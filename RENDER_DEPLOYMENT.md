# Render Free Tier Deployment Guide

## Memory Optimization for 512MB RAM Limit

The Render free tier has a strict 512MB RAM limit. ChromaDB, sentence-transformers, and LangGraph are memory-intensive libraries that can easily exceed this limit.

## Changes Made

### 1. Disabled ChromaDB Initialization
- [main.py](app/main.py): Commented out ChromaDB initialization
- App state variables remain set to None/False
- Server starts without trying to load vector database

### 2. Removed Heavy Imports
- [main.py](app/main.py): Removed `from app.ai.chroma_manager import initialize_chroma`
- [memory_service.py](app/ai/memory_service.py): Commented out chroma_manager imports
- [comment_service.py](app/services/comment_service.py): Commented out chroma_manager imports

### 3. Updated Service Functions
All ChromaDB operations now skip gracefully:
- `create_memory()` - Logs warning, skips embedding storage
- `search_project_memories()` - Returns empty results
- `delete_memory()` - Logs warning, skips embedding deletion
- `create_comment()` - Skips AI memory storage
- `update_comment()` - Skips AI memory update
- `delete_comment()` - Skips AI memory deletion

### 4. Created Lightweight Requirements
`requirements-render.txt` - Excludes:
- chromadb (~200MB)
- sentence_transformers (~500MB with models)
- langgraph (~100MB)
- langchain-openai
- langchain-core
- langchain-groq

## Deployment to Render

1. **Update requirements file in Render dashboard**:
   - Use `requirements-render.txt` instead of `requirements.txt`
   - Or update build command: `pip install -r requirements-render.txt`

2. **Verify deployment**:
   ```bash
   # Check logs for:
   "Server started, ChromaDB initialization is disabled (Render free tier mode)"
   ```

3. **Expected behavior**:
   - ✅ App starts normally
   - ✅ API endpoints work
   - ✅ Database operations succeed
   - ⚠️ Vector search/embeddings disabled
   - ⚠️ AI memory features unavailable

## Features Temporarily Disabled

- Vector similarity search for project memories
- Comment embedding storage
- Semantic search across CRS documents
- LangGraph agent workflows (if used)

## Re-enabling ChromaDB (on VPS)

When you migrate to a VPS with more RAM:

1. **Restore imports**:
   - Uncomment in [main.py](app/main.py#L16)
   - Uncomment in [memory_service.py](app/ai/memory_service.py#L10)
   - Uncomment in [comment_service.py](app/services/comment_service.py#L18)

2. **Restore initialization**:
   - Uncomment the `init_chroma()` function in [main.py](app/main.py#L27-L47)

3. **Restore function calls**:
   - Uncomment all `store_embedding()` calls
   - Uncomment all `search_embeddings()` calls
   - Uncomment all `delete_embedding()` calls

4. **Use full requirements**:
   ```bash
   pip install -r requirements.txt
   ```

## Memory Usage Comparison

| Configuration | Estimated RAM |
|--------------|---------------|
| Full (with ChromaDB) | ~800-1000MB |
| Lightweight (this setup) | ~200-300MB |
| Render Free Tier Limit | 512MB |

## Testing

```bash
# Test that app starts without ChromaDB
python -m uvicorn app.main:app --reload

# Check logs for:
# "Server started, ChromaDB initialization is disabled (Render free tier mode)"
# "ChromaDB disabled - skipping embedding storage for..."
```
