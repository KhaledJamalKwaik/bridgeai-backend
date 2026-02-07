"""
Background CRS generation service with task queuing and retry logic.
Handles progressive real-time updates via EventBus.
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional, Set
from enum import Enum

from sqlalchemy.orm import Session

from app.core.events import event_bus
from app.ai.nodes.template_filler.llm_template_filler import LLMTemplateFiller
from app.services.crs_service import persist_crs_document
from app.models.message import Message, SenderType
from app.models.session_model import SessionModel
from app.models.crs import CRSDocument

logger = logging.getLogger(__name__)


class CRSGenerationStatus(Enum):
    """Status of background CRS generation task"""
    IDLE = "idle"
    QUEUED = "queued"
    GENERATING = "generating"
    COMPLETE = "complete"
    ERROR = "error"


@dataclass
class CRSGenerationTask:
    """Represents a queued CRS generation task"""
    session_id: int
    project_id: int
    user_id: int
    pattern: str
    retry_count: int = 0
    max_retries: int = 3
    created_at: datetime = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow()


class BackgroundCRSGenerator:
    """
    Singleton service that manages background CRS generation tasks.
    
    Features:
    - Task queuing to prevent concurrent updates to same session
    - Retry logic with exponential backoff
    - Progressive update emissions via EventBus
    - High performance with asyncio task management
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._initialized = True
        self.active_tasks: Dict[int, asyncio.Task] = {}  # session_id -> task
        self.task_queue: asyncio.Queue = asyncio.Queue()
        self.processing_sessions: Set[int] = set()
        self.queued_sessions: Set[int] = set()  # Track sessions in queue
        self.session_status: Dict[int, CRSGenerationStatus] = {}
        
        logger.info("BackgroundCRSGenerator initialized")
    
    async def start_worker(self):
        """Start the background worker that processes queued tasks"""
        logger.info("Starting CRS generation worker")
        while True:
            try:
                task: CRSGenerationTask = await self.task_queue.get()
                
                # Skip if already processing this session
                if task.session_id in self.processing_sessions:
                    logger.warning(f"Session {task.session_id} already processing, skipping duplicate task")
                    self.task_queue.task_done()
                    continue
                
                # Mark session as processing
                self.queued_sessions.discard(task.session_id)
                self.processing_sessions.add(task.session_id)
                self.session_status[task.session_id] = CRSGenerationStatus.GENERATING
                
                # Create asyncio task for this generation
                async_task = asyncio.create_task(
                    self._process_task(task)
                )
                self.active_tasks[task.session_id] = async_task
                
                # Wait for completion
                await async_task
                
                # Cleanup
                self.active_tasks.pop(task.session_id, None)
                self.processing_sessions.discard(task.session_id)
                self.task_queue.task_done()
                
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(1)  # Prevent tight loop on persistent errors
    
    async def _process_task(self, task: CRSGenerationTask):
        """Process a single CRS generation task with retry logic"""
        from app.db.session import SessionLocal
        
        db = SessionLocal()
        try:
            await self._generate_crs_with_retry(db, task)
        except Exception as e:
            logger.error(f"Failed to generate CRS for session {task.session_id}: {e}", exc_info=True)
            self.session_status[task.session_id] = CRSGenerationStatus.ERROR
            
            # Publish error event
            await event_bus.publish(task.session_id, {
                "type": "crs_error",
                "error": str(e),
                "retry_count": task.retry_count,
                "timestamp": datetime.utcnow().isoformat()
            })
        finally:
            db.close()
    
    async def _generate_crs_with_retry(self, db: Session, task: CRSGenerationTask):
        """Generate CRS with exponential backoff retry logic"""
        last_error = None
        
        for attempt in range(task.max_retries):
            try:
                await self._generate_crs_progressive(db, task)
                return  # Success
            except Exception as e:
                last_error = e
                task.retry_count = attempt + 1
                
                # Rollback the session to clear any pending transactions
                try:
                    db.rollback()
                except Exception:
                    pass
                
                if attempt < task.max_retries - 1:
                    # Exponential backoff: 2^attempt seconds
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"CRS generation attempt {attempt + 1} failed for session {task.session_id}, "
                        f"retrying in {wait_time}s: {e}"
                    )
                    
                    # Publish retry event
                    await event_bus.publish(task.session_id, {
                        "type": "crs_retry",
                        "attempt": attempt + 1,
                        "max_attempts": task.max_retries,
                        "wait_time": wait_time,
                        "error": str(e)
                    })
                    
                    await asyncio.sleep(wait_time)
                else:
                    logger.error(
                        f"CRS generation failed after {task.max_retries} attempts for session {task.session_id}: {e}",
                        exc_info=True
                    )
        
        # All retries exhausted
        raise last_error
    
    async def _generate_crs_progressive(self, db: Session, task: CRSGenerationTask):
        """
        Generate CRS with progressive updates emitted to EventBus.
        
        Emits events:
        - crs_progress: After each major step (extraction, summary, etc.)
        - crs_complete: When generation finishes successfully
        """
        session_id = task.session_id
        
        # Publish start event
        await event_bus.publish(session_id, {
            "type": "crs_generation_started",
            "session_id": session_id,
            "pattern": task.pattern,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        # Step 1: Gather conversation history
        await event_bus.publish(session_id, {
            "type": "crs_progress",
            "step": "gathering_context",
            "percentage": 10,
            "message": "Gathering conversation context..."
        })
        
        messages = (
            db.query(Message)
            .filter(Message.session_id == session_id)
            .order_by(Message.timestamp.asc())
            .all()
        )
        
        conversation_history = []
        user_inputs = []
        
        for msg in messages:
            if msg.sender_type == SenderType.client:
                conversation_history.append(f"User: {msg.content}")
                user_inputs.append(msg.content)
            else:
                conversation_history.append(f"AI: {msg.content}")
        
        if not user_inputs:
            logger.warning(f"No user inputs found for session {session_id}")
            return
        
        # Step 2: Initialize template filler
        await event_bus.publish(session_id, {
            "type": "crs_progress",
            "step": "initializing",
            "percentage": 20,
            "message": "Initializing CRS template..."
        })
        
        template_filler = LLMTemplateFiller(pattern=task.pattern)
        
        # Step 3: Extract requirements (STREAMING)
        await event_bus.publish(session_id, {
            "type": "crs_progress",
            "step": "extraction",
            "percentage": 30,
            "message": "AI is writing the specification...",
            "is_streaming": True
        })
        
        # Combine all user inputs
        combined_input = "\n\n".join(user_inputs)
        
        # Get existing CRS if any
        session_model = db.query(SessionModel).filter(SessionModel.id == session_id).first()
        existing_crs_content = None
        if session_model and session_model.crs_document_id:
            existing_crs = db.query(CRSDocument).filter(CRSDocument.id == session_model.crs_document_id).first()
            if existing_crs:
                existing_crs_content = existing_crs.content
        
        # Stream fill template
        last_emit_time = 0
        last_autosave_time = 0
        final_result = {}
        autosave_interval = 10.0  # Auto-save draft every 10 seconds
        draft_crs_id = None
        
        async for partial_json in template_filler.fill_template_stream(
            user_input=combined_input,
            conversation_history=conversation_history,
            extracted_fields=existing_crs_content
        ):
            final_result = partial_json
            current_time = asyncio.get_event_loop().time()
            
            # Throttle emissions to ~10Hz (every 100ms) to avoid overwhelming UI
            if current_time - last_emit_time > 0.1:
                await event_bus.publish(session_id, {
                    "type": "crs_partial",
                    "content": json.dumps(partial_json),
                    "timestamp": datetime.utcnow().isoformat()
                })
                last_emit_time = current_time
            
            # Auto-save draft to database every 10 seconds
            if current_time - last_autosave_time > autosave_interval:
                try:
                    crs_content_str = json.dumps(partial_json) if isinstance(partial_json, dict) else partial_json
                    
                    # Update existing draft or create new one
                    if draft_crs_id:
                        # Update existing draft
                        draft_crs = db.query(CRSDocument).filter(CRSDocument.id == draft_crs_id).first()
                        if draft_crs:
                            draft_crs.content = crs_content_str
                            draft_crs.updated_at = datetime.utcnow()
                            db.commit()
                            logger.info(f"Auto-saved draft CRS {draft_crs_id} for session {session_id}")
                    else:
                        # Create new draft
                        draft_crs = persist_crs_document(
                            db,
                            project_id=task.project_id,
                            created_by=task.user_id,
                            content=crs_content_str,
                            summary_points=[],  # Will be filled at completion
                            pattern=task.pattern,
                            field_sources=None,
                            store_embedding=False  # Skip embedding for drafts
                        )
                        draft_crs_id = draft_crs.id
                        
                        # Link to session immediately so refresh can find it
                        session_model.crs_document_id = draft_crs_id
                        db.commit()
                        
                        logger.info(f"Created auto-save draft CRS {draft_crs_id} for session {session_id}")
                        
                        # Notify frontend that draft is now persisted
                        await event_bus.publish(session_id, {
                            "type": "crs_progress",
                            "step": "draft_persisted",
                            "percentage": 35,
                            "message": "Draft saved to database",
                            "crs_document_id": draft_crs_id
                        })
                    
                    last_autosave_time = current_time
                    
                except Exception as e:
                    logger.error(f"Auto-save failed for session {session_id}: {e}")
                    # Don't fail the entire generation on auto-save errors
                    db.rollback()

        # Final full extraction to get completeness metadata and quality checks
        # (Using the batch method once at the end for full validation)
        result = template_filler.fill_template(
            user_input=combined_input,
            conversation_history=conversation_history,
            extracted_fields=existing_crs_content
        )
        
        # Step 4: Emit template final update
        crs_template_dict = result["crs_template"].to_dict() if hasattr(result["crs_template"], "to_dict") else result["crs_template"]
        
        if result.get("is_auto_filled"):
            logger.info(f"CRS for session {session_id} is being AUTO-FILLED (threshold reached)")
        
        # Step 5: Generate summary
        await event_bus.publish(session_id, {
            "type": "crs_progress",
            "step": "summary",
            "percentage": 75,
            "message": "Generating summary...",
            "summary_points": result.get("summary_points", []),
            "overall_summary": result.get("overall_summary", "")
        })
        
        # Step 6: Check completeness
        is_complete = result.get("is_complete", False)
        
        await event_bus.publish(session_id, {
            "type": "crs_progress",
            "step": "completeness_check",
            "percentage": 85,
            "message": "Checking completeness...",
            "is_complete": is_complete,
            "completeness_info": result.get("completeness_info", {})
        })
        
        # Step 7: Persist to database (update existing draft or create new)
        await event_bus.publish(session_id, {
            "type": "crs_progress",
            "step": "persisting",
            "percentage": 90,
            "message": "Finalizing CRS document..."
        })
        
        crs_content_dict = result["crs_template"].to_dict() if hasattr(result["crs_template"], "to_dict") else result["crs_template"]
        crs_content_str = json.dumps(crs_content_dict) if isinstance(crs_content_dict, dict) else crs_content_dict
        
        # Update existing draft with final content and metadata
        if draft_crs_id:
            crs_doc = db.query(CRSDocument).filter(CRSDocument.id == draft_crs_id).first()
            if crs_doc:
                crs_doc.content = crs_content_str
                crs_doc.summary_points = json.dumps(result.get("summary_points", []))
                crs_doc.updated_at = datetime.utcnow()
                
                # Update embedding for final version using create_memory
                try:
                    from app.ai.memory_service import create_memory
                    create_memory(
                        db=db,
                        project_id=task.project_id,
                        text=crs_content_str,
                        source_type="crs",
                        source_id=crs_doc.id,
                    )
                except Exception as e:
                    logger.warning(f"Failed to store embedding for CRS {crs_doc.id}: {e}")
                
                db.commit()
                logger.info(f"Updated existing draft CRS {crs_doc.id} with final content for session {session_id}")
        else:
            # Fallback: create new document if no draft exists
            crs_doc = persist_crs_document(
                db,
                project_id=task.project_id,
                created_by=task.user_id,
                content=crs_content_str,
                summary_points=result.get("summary_points", []),
                pattern=task.pattern,
                field_sources=result.get("field_sources"),
                store_embedding=True
            )
            # Link to session
            session_model.crs_document_id = crs_doc.id
            db.commit()
        
        logger.info(f"CRS document {crs_doc.id} finalized for session {session_id} (complete={is_complete})")
        
        # Step 8: Publish completion
        self.session_status[session_id] = CRSGenerationStatus.COMPLETE
        
        crs_template_final = result["crs_template"].to_dict() if hasattr(result["crs_template"], "to_dict") else result["crs_template"]
        
        await event_bus.publish(session_id, {
            "type": "crs_complete" if is_complete else "crs_updated",
            "percentage": 100,
            "session_id": session_id,
            "is_complete": is_complete,
            "crs_template": json.dumps(crs_template_final),
            "summary_points": result.get("summary_points", []),
            "overall_summary": result.get("overall_summary", ""),
            "completeness_info": result.get("completeness_info", {}),
            "crs_document_id": crs_doc.id,
            "timestamp": datetime.utcnow().isoformat()
        })
        
        logger.info(f"CRS generation complete for session {session_id} (complete={is_complete})")
        
        # Step 9: Generate suggestions if CRS is complete
        if is_complete:
            try:
                from app.ai.nodes.suggestions import suggestions_node
                from app.ai.state import AgentState
                
                # Build state for suggestions
                suggestion_state: AgentState = {
                    "project_id": task.project_id,
                    "user_id": task.user_id,
                    "db": db,
                    "user_input": "CRS complete - generating suggestions",
                    "crs_is_complete": True,
                    "suggestion_trigger": "crs_complete"
                }
                
                # Generate suggestions
                suggestion_result = suggestions_node(suggestion_state)
                suggestions = suggestion_result.get("suggestions", [])
                
                if suggestions:
                    # Publish suggestions event
                    await event_bus.publish(session_id, {
                        "type": "suggestions_generated",
                        "session_id": session_id,
                        "suggestions": suggestions,
                        "trigger": "crs_complete",
                        "timestamp": datetime.utcnow().isoformat()
                    })
                    logger.info(f"Generated {len(suggestions)} suggestions for completed CRS (session={session_id})")
                else:
                    logger.warning(f"No suggestions generated for session {session_id}")
                    
            except Exception as e:
                logger.error(f"Failed to generate suggestions after CRS completion: {str(e)}")
    
    async def queue_generation(
        self,
        session_id: int,
        project_id: int,
        user_id: int,
        pattern: str = "babok",
        max_retries: int = 3
    ) -> bool:
        """
        Queue a CRS generation task.
        
        Returns:
            True if task was queued, False if already processing
        """
        # Check if already processing or queued
        if session_id in self.processing_sessions or session_id in self.queued_sessions:
            logger.debug(f"Session {session_id} already has active or queued CRS generation")
            return False
        
        # Create task
        task = CRSGenerationTask(
            session_id=session_id,
            project_id=project_id,
            user_id=user_id,
            pattern=pattern,
            max_retries=max_retries
        )
        
        # Add to queue
        await self.task_queue.put(task)
        self.queued_sessions.add(session_id)
        self.session_status[session_id] = CRSGenerationStatus.QUEUED
        
        logger.info(f"Queued CRS generation for session {session_id} (pattern={pattern})")
        return True
    
    def get_status(self, session_id: int) -> CRSGenerationStatus:
        """Get current generation status for a session"""
        return self.session_status.get(session_id, CRSGenerationStatus.IDLE)
    
    async def cancel_generation(self, session_id: int) -> bool:
        """Cancel active generation for a session"""
        if session_id in self.active_tasks:
            task = self.active_tasks[session_id]
            task.cancel()
            self.active_tasks.pop(session_id, None)
            self.processing_sessions.discard(session_id)
            self.session_status[session_id] = CRSGenerationStatus.IDLE
            
            logger.info(f"Cancelled CRS generation for session {session_id}")
            return True
        return False


# Global singleton instance
_generator_instance: Optional[BackgroundCRSGenerator] = None
_worker_task: Optional[asyncio.Task] = None


def get_crs_generator() -> BackgroundCRSGenerator:
    """Get the global CRS generator instance"""
    global _generator_instance
    if _generator_instance is None:
        _generator_instance = BackgroundCRSGenerator()
    return _generator_instance


async def start_crs_worker():
    """Start the background CRS worker (should be called on app startup)"""
    global _worker_task
    if _worker_task is None or _worker_task.done():
        generator = get_crs_generator()
        _worker_task = asyncio.create_task(generator.start_worker())
        logger.info("CRS background worker started")
    return _worker_task


async def stop_crs_worker():
    """Stop the background CRS worker (should be called on app shutdown)"""
    global _worker_task
    if _worker_task and not _worker_task.done():
        _worker_task.cancel()
        try:
            await _worker_task
        except asyncio.CancelledError:
            pass
        _worker_task = None
        logger.info("CRS background worker stopped")
