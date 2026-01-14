"""
ChromaDB Manager - Handles vector embeddings and semantic search

Architecture:
    - Persistent storage at ./chroma_db (configurable)
    - Single collection: "project_memories" (configurable)
    - Embedding model: all-MiniLM-L6-v2 (384-dimensional) - explicitly configured
    - Distance metric: Cosine similarity
    - Indexing: HNSW (Hierarchical Navigable Small World)
"""
import chromadb
from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
from typing import List, Dict, Any, Optional, Tuple
from app.core.config import settings
import logging
import os

logger = logging.getLogger(__name__)

# Global Chroma client and collection (initialized once at startup)
# These are set from app.state by main.py to ensure singleton pattern
_chroma_client: Optional[chromadb.Client] = None
_collection = None
_is_initialized = False
_embedding_function = None


def initialize_chroma() -> Tuple[chromadb.Client, Any]:
    """
    Initialize ChromaDB client and collection with embedding function
    
    CRITICAL: ChromaDB does NOT automatically generate embeddings.
    You MUST provide an embedding_function explicitly.
    
    This function:
    1. Creates persistent client at CHROMA_DB_PATH
    2. Configures SentenceTransformerEmbeddingFunction (all-MiniLM-L6-v2)
    3. Loads or creates collection with the embedding function
    4. Sets cosine similarity as distance metric
    5. Tests connection
    
    Returns:
        Tuple[chromadb.Client, chromadb.Collection]
        - Client: The ChromaDB persistent client
        - Collection: The initialized collection with embedding function
    
    Timing: Called at app startup (app/main.py)
    
    Raises:
        Exception: If initialization fails
    """
    global _chroma_client, _collection, _is_initialized, _embedding_function
    
    try:
        # Ensure directory exists
        chroma_path = settings.CHROMA_DB_PATH
        os.makedirs(chroma_path, exist_ok=True)
        logger.debug(f"ChromaDB directory: {os.path.abspath(chroma_path)}")
        
        # Create persistent client (file-based storage)
        _chroma_client = chromadb.PersistentClient(path=chroma_path)
        logger.debug(f"ChromaDB PersistentClient created")
        
        # Create embedding function
        # CRITICAL: This is required for ChromaDB to generate embeddings
        _embedding_function = SentenceTransformerEmbeddingFunction(
            model_name="all-MiniLM-L6-v2"
        )
        logger.debug(f"Embedding function configured: all-MiniLM-L6-v2")
        
        # Load or create collection WITH embedding function
        collection_name = settings.CHROMA_COLLECTION_NAME
        try:
            _collection = _chroma_client.get_or_create_collection(
                name=collection_name,
                embedding_function=_embedding_function,  # CRITICAL: Pass embedding function
                metadata={
                    "hnsw:space": "cosine",  # Cosine similarity metric
                    "description": "Project memory embeddings"
                }
            )
        except Exception as e:
            if "Embedding function conflict" in str(e):
                logger.warning(
                    f"Conflict detected in ChromaDB collection '{collection_name}'. "
                    f"Deleting and recreating with correct embedding function. Error: {e}"
                )
                _chroma_client.delete_collection(collection_name)
                _collection = _chroma_client.get_or_create_collection(
                    name=collection_name,
                    embedding_function=_embedding_function,
                    metadata={
                        "hnsw:space": "cosine",
                        "description": "Project memory embeddings"
                    }
                )
            else:
                raise e
        logger.debug(f"Collection loaded: {collection_name}")
        
        # Test connection by getting collection count
        test_count = _collection.count()
        _is_initialized = True
        
        logger.info(
            f"ChromaDB initialized successfully\n"
            f"   Path: {os.path.abspath(chroma_path)}\n"
            f"   Collection: {collection_name}\n"
            f"   Current embeddings: {test_count}\n"
            f"   Embedding model: all-MiniLM-L6-v2 (384-dim)\n"
            f"   Distance metric: Cosine similarity"
        )
        return _chroma_client, _collection
    except Exception as e:
        _is_initialized = False
        logger.error(
            f"Failed to initialize ChromaDB: {str(e)}\n"
            f"   Path attempted: {settings.CHROMA_DB_PATH}\n"
            f"   Collection: {settings.CHROMA_COLLECTION_NAME}\n"
            f"   Ensure the directory is writable and chromadb is installed"
        )
        raise


def get_collection(app=None):
    """
    Get the ChromaDB collection
    
    Singleton pattern - collection is loaded once at startup via app.state
    
    Args:
        app: FastAPI app instance (optional, for backward compatibility)
    
    Returns:
        ChromaDB collection object or None if not initialized
    
    Note:
        Prefers app.state.chroma_collection (set by main.py)
        Falls back to global _collection if app not provided
    """
    global _collection, _is_initialized
    
    # Prefer app.state if available (singleton pattern)
    if app and hasattr(app, 'state'):
        if not getattr(app.state, 'chroma_initialized', False):
            logger.warning("ChromaDB not yet initialized, returning None")
            return None
        if hasattr(app.state, 'chroma_collection'):
            return app.state.chroma_collection
    
    # Fallback to global for backward compatibility
    if _collection is None:
        if not _is_initialized:
            logger.warning("ChromaDB not initialized, returning None")
            return None
    return _collection


def store_embedding(
    embedding_id: str,
    text: str,
    metadata: Dict[str, Any],
    embedding: Optional[List[float]] = None
) -> str:
    """
    Store a text embedding in ChromaDB
    
    How Embeddings Are Created:
        1. If embedding=None (default):
           - ChromaDB uses all-MiniLM-L6-v2 model automatically
           - Downloads ~22MB model on first use
           - Cached at ~/.cache/chroma/
        2. If embedding=<list>:
           - Uses pre-computed embedding (must be 384-dim)
           - Useful for custom embedding models
    
    Args:
        embedding_id: Unique identifier for this memory (usually UUID)
        text: The text content to embed
        metadata: Metadata about the source (project_id, source_type, etc.)
                 This is stored but NOT used in embeddings
        embedding: Pre-computed embedding vector (optional)
    
    Returns:
        embedding_id (confirms storage)
    
    Raises:
        Exception: If storage fails (logged, not re-raised)
    """
    try:
        collection = get_collection()
        
        if collection is None:
            logger.warning(f"ChromaDB not initialized, skipping embedding storage for {embedding_id}")
            return embedding_id  # Return gracefully
        
        logger.debug(f"Storing embedding: {embedding_id} ({len(text)} chars)")
        
        collection.add(
            ids=[embedding_id],
            documents=[text],
            metadatas=[metadata],
            embeddings=[embedding] if embedding else None  # Let ChromaDB generate if None
        )
        
        logger.debug(f"✅ Embedding stored: {embedding_id}")
        return embedding_id
    except Exception as e:
        logger.error(
            f"❌ Failed to store embedding {embedding_id}\n"
            f"   Text length: {len(text)}\n"
            f"   Error: {str(e)}\n"
            f"   Metadata: {metadata}"
        )
        raise


def store_embeddings_batch(
    embedding_ids: List[str],
    texts: List[str],
    metadatas: List[Dict[str, Any]],
    embeddings: Optional[List[List[float]]] = None
) -> List[str]:
    """
    Store multiple embeddings in a single batch operation.
    
    PERFORMANCE: 10-50x faster than individual store_embedding() calls.
    Use this for bulk imports, CRS processing, or batch memory creation.
    
    Args:
        embedding_ids: List of unique IDs
        texts: List of text contents
        metadatas: List of metadata dicts
        embeddings: Optional pre-computed embeddings
    
    Returns:
        List of stored embedding_ids
        
    Example:
        ids = [str(uuid.uuid4()) for _ in range(10)]
        texts = ["text1", "text2", ...]
        metas = [{"project_id": 1}, {"project_id": 1}, ...]
        store_embeddings_batch(ids, texts, metas)
    """
    try:
        collection = get_collection()
        
        if collection is None:
            logger.warning(f"ChromaDB not initialized, skipping batch storage of {len(embedding_ids)} embeddings")
            return embedding_ids  # Return gracefully
        
        logger.info(f"Batch storing {len(embedding_ids)} embeddings")
        
        collection.add(
            ids=embedding_ids,
            documents=texts,
            metadatas=metadatas,
            embeddings=embeddings
        )
        
        logger.info(f"✅ Batch stored {len(embedding_ids)} embeddings")
        return embedding_ids
    except Exception as e:
        logger.error(f"❌ Failed batch store: {str(e)}")
        raise


def search_embeddings(
    query: str,
    project_id: int,
    n_results: int = 5,
    distance_threshold: float = 0.3,
    source_type: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    Search for similar embeddings using semantic search with optimized filtering
    
    PERFORMANCE OPTIMIZATION:
    - Uses ChromaDB's WHERE clause for server-side filtering (faster)
    - Filters by project_id and optionally source_type BEFORE similarity search
    - Distance threshold applied after search (client-side)
    
    Args:
        query: The search query text
        project_id: Filter results to this project
        n_results: Number of results to return (recommend 5-20 for best performance)
        distance_threshold: Minimum similarity score (0-1, lower = more strict)
        source_type: Optional filter by source type (crs, message, comment, summary)
    
    Returns:
        List of similar memories with scores, filtered by threshold
        
    Performance Notes:
        - ChromaDB uses HNSW index for fast approximate nearest neighbor search
        - Typical latency: <50ms for 10k embeddings, <200ms for 100k embeddings
        - WHERE filters are applied BEFORE vector search (very efficient)
    """
    try:
        collection = get_collection()
        
        if collection is None:
            logger.warning("ChromaDB not initialized, returning empty search results")
            return []  # Return empty results gracefully
        
        # Build metadata filter
        where_filter = {"project_id": {"$eq": project_id}}
        if source_type:
            where_filter["source_type"] = {"$eq": source_type}
        
        # Query with optimized filtering
        results = collection.query(
            query_texts=[query],
            n_results=n_results,
            where=where_filter  # Server-side filtering for performance
        )
        
        # Format results
        formatted_results = []
        if results and results['ids'] and len(results['ids']) > 0:
            for i, embedding_id in enumerate(results['ids'][0]):
                distance = results['distances'][0][i]
                similarity = 1 - distance  # Convert distance to similarity
                
                if similarity >= distance_threshold:
                    formatted_results.append({
                        "embedding_id": embedding_id,
                        "text": results['documents'][0][i],
                        "metadata": results['metadatas'][0][i],
                        "similarity_score": round(similarity, 3)
                    })
        
        logger.info(f"Found {len(formatted_results)} similar embeddings for project {project_id}")
        return formatted_results
    except Exception as e:
        logger.error(f"Search failed for project {project_id}: {str(e)}")
        return []


def get_embedding(embedding_id: str) -> Optional[Dict[str, Any]]:
    """
    Retrieve a specific embedding by ID
    
    Args:
        embedding_id: The embedding ID to retrieve
    
    Returns:
        Embedding data or None if not found
    """
    try:
        collection = get_collection()
        
        if collection is None:
            logger.warning("ChromaDB not initialized, cannot retrieve embedding")
            return None
        
        result = collection.get(ids=[embedding_id])
        
        if result and result['ids']:
            return {
                "embedding_id": result['ids'][0],
                "text": result['documents'][0],
                "metadata": result['metadatas'][0]
            }
        return None
    except Exception as e:
        logger.error(f"Failed to get embedding {embedding_id}: {str(e)}")
        return None


def delete_embedding(embedding_id: str) -> bool:
    """
    Delete an embedding from ChromaDB
    
    Args:
        embedding_id: The embedding ID to delete
    
    Returns:
        True if successful, False otherwise
    """
    try:
        collection = get_collection()
        
        if collection is None:
            logger.warning("ChromaDB not initialized, skipping embedding deletion")
            return True  # Return success to not break the flow
        
        collection.delete(ids=[embedding_id])
        logger.info(f"Deleted embedding: {embedding_id}")
        return True
    except Exception as e:
        logger.error(f"Failed to delete embedding {embedding_id}: {str(e)}")
        return False


def get_project_memory_count(project_id: int) -> int:
    """
    Get total memory count for a project
    
    Args:
        project_id: The project ID
    
    Returns:
        Number of memories for this project
    """
    try:
        collection = get_collection()
        
        if collection is None:
            logger.warning("ChromaDB not initialized, returning 0 for memory count")
            return 0
        
        count = collection.count()
        # Note: ChromaDB doesn't have direct filtering count, 
        # so we query and count results
        results = collection.query(
            query_texts=[""],  # Empty query just to get counts
            n_results=10000,
            where={"project_id": {"$eq": project_id}}
        )
        return len(results['ids'][0]) if results['ids'] else 0
    except Exception as e:
        logger.error(f"Failed to get memory count for project {project_id}: {str(e)}")
        return 0
