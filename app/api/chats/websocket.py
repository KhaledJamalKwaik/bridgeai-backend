"""
Chat WebSocket Module.
Handles real-time WebSocket communication for chat sessions.
"""
import asyncio
import json
from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.message import Message, SenderType
from app.models.session_model import SessionModel
from app.models.user import User
from app.services.permission_service import PermissionService


router = APIRouter()


# WebSocket connection manager
class ConnectionManager:
    def __init__(self):
        # Store active connections per session
        self.active_connections: Dict[int, List[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, session_id: int):
        await websocket.accept()
        if session_id not in self.active_connections:
            self.active_connections[session_id] = []
        self.active_connections[session_id].append(websocket)

    def disconnect(self, websocket: WebSocket, session_id: int):
        if session_id in self.active_connections:
            self.active_connections[session_id].remove(websocket)
            if not self.active_connections[session_id]:
                del self.active_connections[session_id]

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast_to_session(self, message: dict, session_id: int):
        if session_id in self.active_connections:
            message_json = json.dumps(message)
            for connection in self.active_connections[session_id]:
                try:
                    await connection.send_text(message_json)
                except Exception:
                    pass


manager = ConnectionManager()


@router.websocket("/{project_id}/chats/{chat_id}/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    project_id: int,
    chat_id: int,
    token: str = Query(...),
    db: Session = Depends(get_db),
):
    from app.core.config import settings

    safe_db_url = (
        str(settings.DATABASE_URL).replace(
            settings.DATABASE_URL.split(":")[2].split("@")[0], "***"
        )
        if "@" in str(settings.DATABASE_URL)
        else settings.DATABASE_URL
    )
    print(f"[WebSocket] Connecting using DB URL: {safe_db_url}")
    """
    WebSocket endpoint for real-time chat communication.
    
    Client should connect with: ws://host/api/projects/{project_id}/chats/{chat_id}/ws?token={access_token}
    
    Message format (from client):
    {
        "content": "message content",
        "sender_type": "client" | "ba"
    }
    
    Message format (to client):
    {
        "id": 123,
        "session_id": 1,
        "sender_type": "client" | "ai" | "ba",
        "sender_id": 1,
        "content": "message content",
        "timestamp": "2025-12-08T10:30:00Z"
    }
    """

    print(
        f"[WebSocket] Connection attempt - project_id={project_id}, chat_id={chat_id}"
    )

    # Authenticate user via token
    try:
        print("[WebSocket] Decoding token...")
        payload = decode_access_token(token)
        user_id = payload.get("sub")
        print(f"[WebSocket] Token decoded - user_id={user_id}")
        if user_id is None:
            print("[WebSocket] No user_id in token payload")
            await websocket.close(code=1008, reason="Invalid authentication token")
            return

        # Get user from database
        print("[WebSocket] Querying user from database...")
        user = db.query(User).filter(User.id == int(user_id)).first()
        if not user:
            print("[WebSocket] User not found in database")
            await websocket.close(code=1008, reason="User not found")
            return
        print(f"[WebSocket] User found: {user.email}")
    except Exception as e:
        print(f"[WebSocket] Authentication failed: {str(e)}")
        await websocket.close(code=1008, reason="Authentication failed")
        return

    # Verify project access
    try:
        print("[WebSocket] Verifying project access...")
        project = PermissionService.verify_project_access(db, project_id, user.id)
        print("[WebSocket] Project access verified")
    except HTTPException:
        print("[WebSocket] Access denied to project")
        await websocket.close(code=1008, reason="Access denied to project")
        return

    # Verify session exists and belongs to project
    print("[WebSocket] Verifying session...")
    session = (
        db.query(SessionModel)
        .filter(SessionModel.id == chat_id, SessionModel.project_id == project_id)
        .first()
    )

    if not session:
        print("[WebSocket] Chat session not found")
        await websocket.close(code=1008, reason="Chat session not found")
        return

    print(f"[WebSocket] Session verified: {session.name}")

    # Connect to WebSocket
    print("[WebSocket] Accepting connection...")
    await manager.connect(websocket, chat_id)
    print("[WebSocket] Connection established!")

    # Initialize AI graph
    from app.ai.graph import create_graph

    ai_graph = create_graph()

    try:
        while True:
            # Receive message from client
            data = await websocket.receive_text()

            try:
                message_data = json.loads(data)
                content = message_data.get("content", "").strip()
                sender_type_str = message_data.get("sender_type", "client")
                crs_pattern_from_message = message_data.get("crs_pattern")

                if not content:
                    continue

                # Validate sender_type
                try:
                    sender_type = SenderType[sender_type_str]
                except KeyError:
                    await websocket.send_text(
                        json.dumps({"error": f"Invalid sender_type: {sender_type_str}"})
                    )
                    continue

                # Save message to database with retry on lock errors
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        new_message = Message(
                            session_id=chat_id,
                            sender_type=sender_type,
                            sender_id=user.id,
                            content=content,
                        )

                        db.add(new_message)
                        db.commit()
                        db.refresh(new_message)
                        break  # Success
                    except Exception as e:
                        db.rollback()
                        if attempt < max_retries - 1:
                            print(f"[WebSocket] Database error (attempt {attempt + 1}/{max_retries}): {e}")
                            await asyncio.sleep(0.1 * (attempt + 1))  # Exponential backoff
                        else:
                            print(f"[WebSocket] Failed to save message after {max_retries} attempts: {e}")
                            await websocket.send_text(
                                json.dumps({"error": "Failed to save message. Please try again."})
                            )
                            continue

                # Broadcast message to all connected clients in this session
                message_response = {
                    "type": "message",
                    "id": new_message.id,
                    "session_id": new_message.session_id,
                    "sender_type": new_message.sender_type.value,
                    "sender_id": new_message.sender_id,
                    "content": new_message.content,
                    "timestamp": new_message.timestamp.isoformat(),
                }

                await manager.broadcast_to_session(message_response, chat_id)

                # ---------------------------------------------------------
                # AI RESPONSE LOGIC
                # ---------------------------------------------------------
                # Only respond to client messages to avoid loops
                if sender_type == SenderType.client:
                    try:
                        print(f"[WebSocket] Invoking AI for message: {content}")

                        # Send thinking status
                        await manager.broadcast_to_session({
                            "type": "status",
                            "status": "thinking",
                            "is_generating": True
                        }, chat_id)

                        # Fetch conversation history (get last 20 messages)
                        history_messages = (
                            db.query(Message)
                            .filter(Message.session_id == chat_id)
                            .order_by(Message.timestamp.desc())
                            .limit(20)
                            .all()
                        )

                        # Reverse to chronological order (Oldest -> Newest)
                        history_messages.reverse()

                        history_strings = []
                        for msg in history_messages:
                            role = (
                                "User" if msg.sender_type == SenderType.client else "AI"
                            )
                            history_strings.append(f"{role}: {msg.content}")

                        # Prepare state for AI
                        # CRS pattern priority: message > existing CRS > default
                        crs_pattern_value = "babok"  # default
                        
                        # If pattern was sent in message, use it
                        if crs_pattern_from_message:
                            crs_pattern_value = crs_pattern_from_message
                        # Otherwise, get from the latest CRS for this chat session
                        elif session.crs_document_id:
                            from app.models.crs import CRSDocument
                            crs_doc = db.query(CRSDocument).filter(
                                CRSDocument.id == session.crs_document_id
                            ).first()
                            if crs_doc and crs_doc.pattern:
                                crs_pattern_value = crs_doc.pattern.value
                        
                        state = {
                            "user_input": content,
                            "conversation_history": history_strings,
                            "extracted_fields": {},
                            "project_id": project_id,
                            "db": db,
                            "message_id": new_message.id,  # Pass message ID for memory linking
                            "user_id": user.id,
                            "crs_pattern": crs_pattern_value,
                        }

                        # Invoke graph (using ainvoke if available, otherwise synchronous invoke)
                        # StateGraph usually supports .invoke()
                        result = await ai_graph.ainvoke(state)
                        
                        # Defensive handling: ensure result is a dictionary
                        if isinstance(result, str):
                            # If result is a string, wrap it
                            result = {"output": result}
                        elif not isinstance(result, dict):
                            # If result is neither string nor dict, create default
                            result = {"output": "I didn't understand that."}

                        ai_output = result.get("output", "I didn't understand that.")
                        
                        # ---------------------------------------------------------
                        # BACKGROUND CRS GENERATION THRESHOLD CHECK
                        # ---------------------------------------------------------
                        # Start background CRS generation if:
                        # 1. Intent is "requirement" (not greeting/question)
                        # 2. Message count >= 3 (title + idea + at least one answer)
                        # 3. No active generation is running
                        intent = result.get("intent", "requirement")
                        if intent == "requirement":
                            try:
                                from app.services.background_crs_generator import get_crs_generator, CRSGenerationStatus
                                
                                generator = get_crs_generator()
                                current_status = generator.get_status(chat_id)
                                
                                # Count messages in this session
                                message_count = db.query(Message).filter(
                                    Message.session_id == chat_id,
                                    Message.sender_type == SenderType.client
                                ).count()
                                
                                # Only start if IDLE/COMPLETE/ERROR and have at least one message
                                # This ensures the document is filled gradually as the chat progresses.
                                if current_status in [CRSGenerationStatus.IDLE, CRSGenerationStatus.COMPLETE, CRSGenerationStatus.ERROR] and message_count >= 1:
                                    # Queue background generation
                                    queued = await generator.queue_generation(
                                        session_id=chat_id,
                                        project_id=project_id,
                                        user_id=user.id,
                                        pattern=crs_pattern_value,
                                        max_retries=3
                                    )
                                    
                                    if queued:
                                        print(f"[WebSocket] Queued background CRS generation for session {chat_id}")
                                        
                                        # Notify client that CRS generation started
                                        await manager.broadcast_to_session({
                                            "type": "crs_generation_started",
                                            "session_id": chat_id,
                                            "message": "CRS generation started in background"
                                        }, chat_id)
                                    else:
                                        print(f"[WebSocket] CRS generation already active for session {chat_id}")
                                        
                            except Exception as e:
                                print(f"[WebSocket] Failed to start background CRS generation: {str(e)}")

                        # Save AI response to database
                        ai_message = Message(
                            session_id=chat_id,
                            sender_type=SenderType.ai,
                            sender_id=None,  # AI has no user ID
                            content=ai_output,
                        )

                        db.add(ai_message)
                        db.commit()
                        db.refresh(ai_message)
                        
                        # Check if suggestions were generated and send as separate message
                        suggestions = result.get("suggestions", [])
                        if suggestions:
                            # Format suggestions as a readable message
                            suggestions_text = "\n\n💡 **Here are some creative suggestions for your project:**\n\n"
                            
                            # Group by category
                            categories = {}
                            for suggestion in suggestions:
                                category = suggestion.get("category", "OTHER")
                                if category not in categories:
                                    categories[category] = []
                                categories[category].append(suggestion)
                            
                            # Format each category
                            category_labels = {
                                "ADDITIONAL_FEATURES": "🎯 Additional Features",
                                "ALTERNATIVE_SCENARIOS": "🔄 Alternative Scenarios",
                                "INTEGRATION_OPPORTUNITIES": "🔗 Integration Opportunities",
                                "ENHANCEMENT_IDEAS": "✨ Enhancement Ideas",
                                "FUTURE_CONSIDERATIONS": "🔮 Future Considerations",
                                "OTHER": "💭 Other Suggestions"
                            }
                            
                            for category, items in categories.items():
                                label = category_labels.get(category, category)
                                suggestions_text += f"\n**{label}**\n"
                                for idx, item in enumerate(items, 1):
                                    title = item.get("title", "Untitled")
                                    description = item.get("description", "")
                                    suggestions_text += f"{idx}. **{title}**\n   {description}\n\n"
                            
                            # Save suggestions as a separate AI message
                            suggestions_message = Message(
                                session_id=chat_id,
                                sender_type=SenderType.ai,
                                sender_id=None,
                                content=suggestions_text,
                            )
                            db.add(suggestions_message)
                            db.commit()
                            db.refresh(suggestions_message)
                            
                            # Broadcast suggestions message
                            await manager.broadcast_to_session({
                                "type": "message",
                                "id": suggestions_message.id,
                                "session_id": suggestions_message.session_id,
                                "sender_type": suggestions_message.sender_type.value,
                                "sender_id": suggestions_message.sender_id,
                                "content": suggestions_message.content,
                                "timestamp": suggestions_message.timestamp.isoformat(),
                                "is_suggestions": True,
                                "suggestions_metadata": {
                                    "count": len(suggestions),
                                    "trigger": result.get("suggestion_trigger", "unknown")
                                }
                            }, chat_id)
                            
                            logger.info(f"Sent {len(suggestions)} suggestions via chat for session {chat_id}")

                        # Broadcast AI response with optional CRS metadata
                        # CRS metadata is included when the template filler generates a complete CRS
                        ai_response_payload = {
                            "type": "message",
                            "id": ai_message.id,
                            "session_id": ai_message.session_id,
                            "sender_type": ai_message.sender_type.value,
                            "sender_id": ai_message.sender_id,
                            "content": ai_message.content,
                            "timestamp": ai_message.timestamp.isoformat(),
                        }

                        # Include CRS metadata if generated
                        ai_response_payload["crs"] = {
                            "is_complete": result.get("crs_is_complete", False),
                            "summary_points": result.get("summary_points", []),
                            "quality_summary": result.get("quality_summary"),
                        }

                        if result.get("crs_is_complete"):
                            crs_doc_id = result.get("crs_document_id")
                            ai_response_payload["crs"].update({
                                "crs_document_id": crs_doc_id,
                                "version": result.get("crs_version"),
                            })

                            # Link the CRS document to this chat session
                            if crs_doc_id:
                                session = (
                                    db.query(SessionModel)
                                    .filter(SessionModel.id == chat_id)
                                    .first()
                                )
                                if session and not session.crs_document_id:
                                    session.crs_document_id = crs_doc_id
                                    db.commit()
                                    print(
                                        f"[WebSocket] Linked CRS {crs_doc_id} to session {chat_id}"
                                    )

                        await manager.broadcast_to_session(ai_response_payload, chat_id)
                        print(f"[WebSocket] AI response sent: {ai_output}")

                        # Note: CRS updates are now handled by background generation service
                        # The EventBus will receive progressive updates from BackgroundCRSGenerator
                        # Legacy CRS update code removed to prevent conflicts with background generation

                        # Count total messages to verify storage
                        total_msg_count = (
                            db.query(Message)
                            .filter(Message.session_id == chat_id)
                            .count()
                        )
                        print(
                            f"[WebSocket] Total messages in DB for session {chat_id}: {total_msg_count}"
                        )

                    except Exception as e:
                        import traceback
                        error_traceback = traceback.format_exc()
                        print(f"[WebSocket] AI generation error: {str(e)}")
                        print(f"[WebSocket] Full traceback:\n{error_traceback}")
                        # Optionally send error to client or just log it

            except json.JSONDecodeError:
                await websocket.send_text(json.dumps({"error": "Invalid JSON format"}))
            except Exception as e:
                print(f"[WebSocket] Error processing message: {str(e)}")
                await websocket.send_text(
                    json.dumps({"error": f"Error processing message: {str(e)}"})
                )

    except WebSocketDisconnect:
        manager.disconnect(websocket, chat_id)
    except Exception as e:
        print(f"[WebSocket] Connection error: {str(e)}")
        manager.disconnect(websocket, chat_id)
