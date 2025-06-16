#!/usr/bin/env python3
"""
Script to add missing admin endpoints to api.py for data sync fix.
Run this to patch the API file with the required endpoints.
"""
import re

# Read the current api.py file
with open('src/memory_service/api.py', 'r') as f:
    content = f.read()

# Find where to insert (after the graph endpoints, around line 1950)
insert_point = content.find('@app.post("/graph/query")')
if insert_point == -1:
    print("Could not find insertion point!")
    exit(1)

# Find the end of the graph/query endpoint
end_point = content.find('\n@app.', insert_point + 1)
if end_point == -1:
    end_point = len(content)

# Admin endpoints code
admin_endpoints = '''
    @app.post("/admin/refresh-stats")
    async def refresh_stats(
        admin_key: str,
        store: UnifiedVectorStore = Depends(get_store)
    ):
        """
        Manually refresh stats from all providers.
        
        This fixes the synchronization issue where stats show 0 memories.
        """
        # Validate admin key
        if admin_key != os.getenv("ADMIN_KEY", "refresh-stats-2025"):
            raise HTTPException(status_code=403, detail="Invalid admin key")
        
        try:
            # Get old total for comparison
            old_total = store.stats.get('total_stores', 0)
            
            # Refresh stats from providers
            new_total = await store.refresh_stats()
            
            return {
                "status": "success",
                "old_total_memories": old_total,
                "new_total_memories": new_total,
                "difference": new_total - old_total,
                "message": f"Stats refreshed successfully. Found {new_total} memories.",
                "providers": store.stats.get('provider_usage', {})
            }
            
        except Exception as e:
            logger.error(f"Failed to refresh stats: {e}")
            raise HTTPException(status_code=500, detail=f"Failed to refresh stats: {str(e)}")

    @app.delete("/memories/cache")
    async def clear_query_cache(store: UnifiedVectorStore = Depends(get_store)):
        """Clear the query cache to ensure fresh results."""
        try:
            cache_size_before = len(store.query_cache) if isinstance(store.query_cache, dict) else 0
            
            # Clear cache
            if isinstance(store.query_cache, dict):
                store.query_cache.clear()
            else:
                # Redis cache
                store.query_cache.flushdb()
            
            return {
                "status": "success",
                "cache_size_before": cache_size_before,
                "cache_size_after": 0,
                "message": "Query cache cleared successfully"
            }
            
        except Exception as e:
            logger.error(f"Failed to clear cache: {e}")
            raise HTTPException(status_code=500, detail="Failed to clear cache")

    @app.get("/emergency/find-all-memories")
    async def emergency_find_all(
        limit: int = 100,
        store: UnifiedVectorStore = Depends(get_store)
    ):
        """
        Emergency endpoint to directly query all memories from the database.
        
        Bypasses all caching and vector operations for diagnostic purposes.
        """
        try:
            # Get pgvector provider
            pgvector = store.providers.get('pgvector')
            if not pgvector or not pgvector.enabled:
                raise HTTPException(status_code=503, detail="PgVector provider not available")
            
            # Direct query
            async with pgvector.connection_pool.acquire() as conn:
                rows = await conn.fetch(f"""
                    SELECT id, content, metadata, importance_score, created_at
                    FROM {pgvector.table_name}
                    ORDER BY created_at DESC
                    LIMIT $1
                """, limit)
                
                total_count = await conn.fetchval(f"SELECT COUNT(*) FROM {pgvector.table_name}")
            
            return {
                "status": "success",
                "total_memories_found": total_count,
                "memories": [
                    {
                        "id": str(row['id']),
                        "content_preview": row['content'][:100] + "..." if len(row['content']) > 100 else row['content'],
                        "importance_score": float(row['importance_score']),
                        "created_at": row['created_at'].isoformat() if row['created_at'] else None
                    }
                    for row in rows[:10]  # Show first 10 as preview
                ],
                "message": f"Found {total_count} memories via direct database query"
            }
            
        except Exception as e:
            logger.error(f"Emergency search failed: {e}")
            raise HTTPException(status_code=500, detail=f"Emergency search failed: {str(e)}")

'''

# Insert the admin endpoints
new_content = content[:end_point] + admin_endpoints + '\n' + content[end_point:]

# Write back the modified file
with open('src/memory_service/api.py', 'w') as f:
    f.write(new_content)

print("✅ Admin endpoints added successfully!")
print("Next steps:")
print("1. Review the changes: git diff src/memory_service/api.py")
print("2. Test locally: poetry run uvicorn src.memory_service.api:app --reload")
print("3. Deploy: git add -A && git commit -m 'fix: Add admin endpoints for data sync' && git push")