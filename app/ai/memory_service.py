"""
Memory Service - Unified interface for MySQL + ChromaDB
Handles storing and retrieving memories with embeddings
"""
import uuid
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.ai_memory_index import AIMemoryIndex, SourceType
# ChromaDB imports disabled to save memory on Render free tier
# from app.ai.chroma_manager import store_embedding, search_embeddings, delete_embedding
import logging

logger = logging.getLogger(__name__)


def create_memory(
    db: Session,
    project_id: int,
    text: str,
    source_type: str,
    source_id: int,
    metadata: Optional[Dict[str, Any]] = None
) -> Optional[AIMemoryIndex]:
    """
    Store a memory in both MySQL and ChromaDB using two-phase commit pattern
    
    Transaction Safety:
    1. MySQL record created and flushed (Phase 1)
    2. ChromaDB embedding stored (Phase 2)
    3. If Phase 2 fails, Phase 1 is rolled back
    4. If both succeed, both are committed
    
    Args:
        db: Database session
        project_id: Project this memory belongs to
        text: The text content
        source_type: Type of source (crs, message, comment, summary)
        source_id: ID of the source
        metadata: Additional metadata to store
    
    Returns:
        AIMemoryIndex object or None if failed
    """
    embedding_id = None
    try:
        # ========== PHASE 1: MySQL Preparation ==========
        # Generate unique embedding ID
        embedding_id = str(uuid.uuid4())
        
        # Create MySQL record
        memory = AIMemoryIndex(
            project_id=project_id,
            source_type=SourceType[source_type],
            source_id=source_id,
            embedding_id=embedding_id
        )
        
        db.add(memory)
        db.flush()  # Get the memory ID before committing (but don't commit yet)
        
        logger.debug(f"MySQL record flushed for embedding {embedding_id}")
        
        # Prepare ChromaDB metadata
        chroma_metadata = {
            "project_id": project_id,
            "source_type": source_type,
            "source_id": source_id,
            "memory_id": memory.id,
            "created_at": datetime.utcnow().isoformat()
        }
        if metadata:
            chroma_metadata.update(metadata)
        
        # ========== PHASE 2: ChromaDB Storage ==========
        # ChromaDB disabled for Render free tier - skip embedding storage
        logger.warning(f"ChromaDB disabled - skipping embedding storage for {embedding_id}")
        # store_embedding(
        #     embedding_id=embedding_id,
        #     text=text,
        #     metadata=chroma_metadata
        # )
        # logger.debug(f"Embedding stored in ChromaDB for {embedding_id}")
        
        # ========== COMMIT: Both systems ==========
        db.commit()
        logger.info(f"✅ Memory created: {embedding_id} (project={project_id}, source={source_type})")
        return memory
    
    except Exception as e:
        # If anything fails, rollback MySQL changes
        db.rollback()
        logger.error(
            f"❌ Failed to create memory for project {project_id}\n"
            f"   Embedding ID: {embedding_id}\n"
            f"   Error: {str(e)}\n"
            f"   Action: MySQL rolled back to prevent orphaned records"
        )
        return None


def retrieve_memory(
    db: Session,
    embedding_id: str
) -> Optional[Dict[str, Any]]:
    """
    Retrieve a memory by embedding ID
    
    Args:
        db: Database session
        embedding_id: The embedding ID
    
    Returns:
        Combined MySQL + ChromaDB data or None
    """
    try:
        # Get MySQL record
        memory = db.query(AIMemoryIndex).filter(
            AIMemoryIndex.embedding_id == embedding_id
        ).first()
        
        if not memory:
            return None
        
        return {
            "memory_id": memory.id,
            "project_id": memory.project_id,
            "source_type": memory.source_type.value,
            "source_id": memory.source_id,
            "embedding_id": embedding_id,
            "created_at": memory.created_at.isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to retrieve memory {embedding_id}: {str(e)}")
        return None


def search_project_memories(
    db: Session,
    project_id: int,
    query: str,
    limit: int = 5,
    similarity_threshold: float = 0.3
) -> List[Dict[str, Any]]:
    """
    Search project memories using semantic search
    
    Args:
        db: Database session
        project_id: Project to search in
        query: Search query
        limit: Max results to return
        similarity_threshold: Minimum similarity score
    
    Returns:
        List of relevant memories with similarity scores
    """
    try:
        # ChromaDB disabled for Render free tier - return empty results
        logger.warning(f"ChromaDB disabled - returning empty search results for project {project_id}")
        return []
        
        # Search ChromaDB
        # chroma_results = search_embeddings(
        #     query=query,
        #     project_id=project_id,
        #     n_results=limit,
        #     distance_threshold=similarity_threshold
        # )
        
        # Enrich with MySQL data
        enriched_results = []
        for result in chroma_results:
            embedding_id = result['embedding_id']
            memory = db.query(AIMemoryIndex).filter(
                AIMemoryIndex.embedding_id == embedding_id
            ).first()
            
            if memory:
                enriched_results.append({
                    "memory_id": memory.id,
                    "project_id": memory.project_id,
                    "source_type": memory.source_type.value,
                    "source_id": memory.source_id,
                    "embedding_id": embedding_id,
                    "text": result['text'],
                    "similarity_score": result['similarity_score'],
                    "created_at": memory.created_at.isoformat()
                })
        
        logger.info(f"Found {len(enriched_results)} relevant memories for project {project_id}")
        return enriched_results
    except Exception as e:
        logger.error(f"Memory search failed for project {project_id}: {str(e)}")
        return []


def delete_memory(
    db: Session,
    embedding_id: str
) -> bool:
    """
    Delete a memory from both MySQL and ChromaDB
    
    Args:
        db: Database session
        embedding_id: The embedding ID to delete
    
    Returns:
        True if successful, False otherwise
    """
    try:
        # Delete from MySQL
        memory = db.query(AIMemoryIndex).filter(
            AIMemoryIndex.embedding_id == embedding_id
        ).first()
        
        if memory:
            db.delete(memory)
            db.flush()
        
        # ChromaDB disabled for Render free tier - skip embedding deletion
        logger.warning(f"ChromaDB disabled - skipping embedding deletion for {embedding_id}")
        # delete_embedding(embedding_id)
        
        db.commit()
        logger.info(f"Deleted memory {embedding_id}")
        return True
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to delete memory {embedding_id}: {str(e)}")
        return False


def get_project_memory_summary(
    db: Session,
    project_id: int
) -> Dict[str, Any]:
    """
    Get memory statistics for a project
    
    Args:
        db: Database session
        project_id: Project ID
    
    Returns:
        Memory statistics
    """
    try:
        memories = db.query(AIMemoryIndex).filter(
            AIMemoryIndex.project_id == project_id
        ).all()
        
        # Count by source type
        source_counts = {}
        for memory in memories:
            source_type = memory.source_type.value
            source_counts[source_type] = source_counts.get(source_type, 0) + 1
        
        return {
            "project_id": project_id,
            "total_memories": len(memories),
            "by_source_type": source_counts,
            "oldest_memory": min([m.created_at for m in memories]).isoformat() if memories else None,
            "newest_memory": max([m.created_at for m in memories]).isoformat() if memories else None
        }
    except Exception as e:
        logger.error(f"Failed to get memory summary for project {project_id}: {str(e)}")
        return {
            "project_id": project_id,
            "total_memories": 0,
            "by_source_type": {},
            "error": str(e)
        }
