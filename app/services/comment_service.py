"""
Comment service for CRS feedback management.
"""

import logging
from typing import List, Optional
from sqlalchemy.orm import Session
from sqlalchemy import desc

from app.models.comment import Comment
from app.models.crs import CRSDocument
from app.models.user import User

logger = logging.getLogger(__name__)


import uuid
# ChromaDB imports disabled to save memory on Render free tier
# from app.ai import chroma_manager
from app.models.ai_memory_index import AIMemoryIndex, SourceType

def create_comment(
    db: Session,
    *,
    crs_id: int,
    author_id: int,
    content: str
) -> Comment:
    """
    Create a new comment on a CRS document.
    
    Args:
        db: Database session
        crs_id: ID of the CRS document to comment on
        author_id: ID of the user creating the comment
        content: Comment text content
        
    Returns:
        Created Comment object
        
    Raises:
        ValueError: If CRS document not found
    """
    # Verify CRS document exists
    crs = db.query(CRSDocument).filter(CRSDocument.id == crs_id).first()
    if not crs:
        raise ValueError(f"CRS document with id={crs_id} not found")
    
    comment = Comment(
        crs_id=crs_id,
        author_id=author_id,
        content=content
    )
    
    db.add(comment)
    db.commit()
    db.refresh(comment)
    
    logger.info(f"Comment {comment.id} created on CRS {crs_id} by user {author_id}")
    
    # ChromaDB disabled for Render free tier - skip AI memory storage
    logger.debug(f"ChromaDB disabled - skipping AI memory storage for comment {comment.id}")
    # Store in AI Memory (ChromaDB)
    # try:
    #     embedding_id = str(uuid.uuid4())
    #     
    #     # Get author details for metadata
    #     author = db.query(User).filter(User.id == author_id).first()
    #     author_role = author.role.value if author else "unknown"
    #     
    #     # Store in Vector DB
    #     chroma_manager.store_embedding(
    #         embedding_id=embedding_id,
    #         text=content,
    #         metadata={
    #             "project_id": crs.project_id,
    #             "source_type": SourceType.comment.value,
    #             "source_id": comment.id,
    #             "author_id": author_id,
    #             "author_role": author_role,
    #             "crs_id": crs_id
    #         }
    #     )
    #     
    #     # Create Index Record
    #     index_record = AIMemoryIndex(
    #         project_id=crs.project_id,
    #         source_type=SourceType.comment,
    #         source_id=comment.id,
    #         embedding_id=embedding_id
    #     )
    #     db.add(index_record)
    #     db.commit()
    #     logger.info(f"Comment {comment.id} stored in AI memory with id {embedding_id}")
    #     
    # except Exception as e:
    #     logger.error(f"Failed to store comment {comment.id} in AI memory: {str(e)}")
    #     # We don't rollback the comment creation as it's the primary action
    #     pass
    
    return comment


def get_comments_by_crs(
    db: Session,
    *,
    crs_id: int,
    skip: int = 0,
    limit: int = 100
) -> List[Comment]:
    """
    Retrieve all comments for a specific CRS document.
    
    Args:
        db: Database session
        crs_id: ID of the CRS document
        skip: Number of records to skip (pagination)
        limit: Maximum number of records to return
        
    Returns:
        List of Comment objects ordered by creation time (newest first)
    """
    return (
        db.query(Comment)
        .filter(Comment.crs_id == crs_id)
        .order_by(desc(Comment.created_at))
        .offset(skip)
        .limit(limit)
        .all()
    )


def get_comment_by_id(
    db: Session,
    *,
    comment_id: int
) -> Optional[Comment]:
    """
    Retrieve a specific comment by ID.
    
    Args:
        db: Database session
        comment_id: ID of the comment
        
    Returns:
        Comment object or None if not found
    """
    return db.query(Comment).filter(Comment.id == comment_id).first()


def update_comment(
    db: Session,
    *,
    comment_id: int,
    content: str
) -> Comment:
    """
    Update the content of an existing comment.
    
    Args:
        db: Database session
        comment_id: ID of the comment to update
        content: New comment content
        
    Returns:
        Updated Comment object
        
    Raises:
        ValueError: If comment not found
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        raise ValueError(f"Comment with id={comment_id} not found")
    
    comment.content = content
    db.commit()
    db.refresh(comment)
    
    logger.info(f"Comment {comment_id} updated")
    
    # ChromaDB disabled for Render free tier - skip AI memory update
    logger.debug(f"ChromaDB disabled - skipping AI memory update for comment {comment_id}")
    # Update in AI Memory
    # try:
    #     # Find associated index record
    #     index_record = db.query(AIMemoryIndex).filter(
    #         AIMemoryIndex.source_type == SourceType.comment,
    #         AIMemoryIndex.source_id == comment_id
    #     ).first()
    #     
    #     if index_record:
    #         # Get CRS project_id (need to join or fetch)
    #         crs = db.query(CRSDocument).filter(CRSDocument.id == comment.crs_id).first()
    #         project_id = crs.project_id if crs else 0
    #         
    #         author = db.query(User).filter(User.id == comment.author_id).first()
    #         author_role = author.role.value if author else "unknown"
    #         
    #         # Simple re-store (upsert)
    #         chroma_manager.store_embedding(
    #             embedding_id=index_record.embedding_id,
    #             text=content,
    #             metadata={
    #                 "project_id": project_id,
    #                 "source_type": SourceType.comment.value,
    #                 "source_id": comment_id,
    #                 "author_id": comment.author_id,
    #                 "author_role": author_role,
    #                 "crs_id": comment.crs_id
    #             }
    #         )
    #         logger.info(f"Comment {comment_id} updated in AI memory")
    #         
    # except Exception as e:
    #     logger.error(f"Failed to update comment {comment_id} in AI memory: {str(e)}")
    
    return comment


def delete_comment(
    db: Session,
    *,
    comment_id: int
) -> bool:
    """
    Delete a comment.
    
    Args:
        db: Database session
        comment_id: ID of the comment to delete
        
    Returns:
        True if deleted, False if not found
    """
    comment = db.query(Comment).filter(Comment.id == comment_id).first()
    if not comment:
        return False
    
    # ChromaDB disabled for Render free tier - skip AI memory deletion
    logger.debug(f"ChromaDB disabled - skipping AI memory deletion for comment {comment_id}")
    # Delete from AI Memory first (to retrieve index before deleting comment if needed, though index likely remains)
    # try:
    #     index_record = db.query(AIMemoryIndex).filter(
    #         AIMemoryIndex.source_type == SourceType.comment,
    #         AIMemoryIndex.source_id == comment_id
    #     ).first()
    #     
    #     if index_record:
    #         chroma_manager.delete_embedding(index_record.embedding_id)
    #         db.delete(index_record)
    #         # We don't commit yet, we commit with comment deletion to be atomic-ish
    # except Exception as e:
    #     logger.error(f"Failed to delete comment {comment_id} from AI memory: {str(e)}")

    db.delete(comment)
    db.commit()
    
    logger.info(f"Comment {comment_id} deleted")
    
    return True


def get_comments_count_by_crs(
    db: Session,
    *,
    crs_id: int
) -> int:
    """
    Get the total count of comments for a CRS document.
    
    Args:
        db: Database session
        crs_id: ID of the CRS document
        
    Returns:
        Total number of comments
    """
    return db.query(Comment).filter(Comment.crs_id == crs_id).count()
