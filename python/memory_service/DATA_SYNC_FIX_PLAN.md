# Core Nexus Data Synchronization Fix Plan

## Executive Summary

The Core Nexus Memory Service has a critical data synchronization issue where the health endpoint reports 0 memories despite the PgVector database containing 1,095 memories. This is caused by the stats counter starting at 0 on service initialization and never syncing with the actual database count. The issue affects monitoring and health checks but does NOT affect actual data storage or retrieval functionality.

**Impact**: Medium - Monitoring shows incorrect data, but core functionality works
**Urgency**: High - Confuses users and affects system observability
**Estimated Time**: 2-4 hours for complete fix and verification

## Root Cause Analysis

### 1. **Initialization Problem** (Line 81-93 in unified_store.py)
```python
self.stats = {
    'total_stores': 0,  # ← Starts at 0, never synced with DB
    'total_queries': 0,
    'provider_usage': {p.name: 0 for p in providers},
    ...
}
```
The stats dictionary initializes `total_stores` to 0 and only increments when new memories are stored through the API.

### 2. **Missing Initial Sync** 
The service doesn't query the database on startup to get the actual count of existing memories. While there's an `_sync_initial_stats()` method scheduled, it appears to not be working correctly or the endpoint was deployed without this fix.

### 3. **Health Endpoint Issue** (Line 400 in api.py)
```python
total_memories=health_data['stats']['total_stores'],  # Returns 0
```
The health endpoint uses the unsynced counter instead of querying providers for actual counts.

### 4. **Missing Admin Endpoints**
The `/admin/refresh-stats` endpoint referenced in the fix scripts is not present in the current API code, suggesting incomplete deployment.

## Detailed Fix Implementation Plan

### Step 1: Add Missing Admin Endpoints (PRIORITY 1)

Add these endpoints to `api.py` after line 1799:

```python
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
        
        # Use emergency search
        from .search_fix import EmergencySearchFix
        emergency_search = EmergencySearchFix(pgvector.connection_pool)
        
        # Get all memories
        memories = await emergency_search.emergency_search_all(limit=limit)
        
        # Get diagnostics
        diagnostics = await emergency_search.ensure_all_memories_visible()
        
        return {
            "status": "success",
            "total_memories_found": len(memories),
            "memories": [
                {
                    "id": str(mem.id),
                    "content_preview": mem.content[:100] + "..." if len(mem.content) > 100 else mem.content,
                    "importance_score": mem.importance_score,
                    "created_at": mem.created_at
                }
                for mem in memories[:10]  # Show first 10 as preview
            ],
            "diagnostics": diagnostics,
            "message": f"Found {len(memories)} memories via direct database query"
        }
        
    except Exception as e:
        logger.error(f"Emergency search failed: {e}")
        raise HTTPException(status_code=500, detail=f"Emergency search failed: {str(e)}")
```

### Step 2: Fix Initial Stats Sync (PRIORITY 1)

Update the `_sync_initial_stats` method in `unified_store.py` (line 625):

```python
async def _sync_initial_stats(self):
    """Synchronize initial stats with actual database counts."""
    try:
        # Wait for providers to fully initialize
        await asyncio.sleep(2)
        
        logger.info("Syncing initial stats from providers...")
        
        # Get actual counts from each provider
        total_memories = 0
        provider_counts = {}
        
        for name, provider in self.providers.items():
            if provider.enabled:
                try:
                    # Try multiple methods to get count
                    count = 0
                    
                    # Method 1: Use get_stats if available
                    if hasattr(provider, 'get_stats'):
                        stats = await provider.get_stats()
                        count = stats.get('total_memories', 0)
                    
                    # Method 2: Direct health check
                    if count == 0 and hasattr(provider, 'health_check'):
                        health = await provider.health_check()
                        if 'details' in health and 'total_vectors' in health['details']:
                            count = health['details']['total_vectors']
                    
                    # Method 3: For pgvector, direct query
                    if count == 0 and name == 'pgvector' and hasattr(provider, 'connection_pool'):
                        async with provider.connection_pool.acquire() as conn:
                            count = await conn.fetchval("SELECT COUNT(*) FROM vector_memories")
                    
                    if count > 0:
                        total_memories += count
                        provider_counts[name] = count
                        logger.info(f"Provider {name} has {count} memories")
                        
                except Exception as e:
                    logger.warning(f"Failed to get stats from {name}: {e}")
                    provider_counts[name] = 0
        
        # Update our stats with the actual count
        if total_memories > 0:
            self.stats['total_stores'] = total_memories
            # Update provider usage counts
            for name, count in provider_counts.items():
                if count > 0:
                    self.stats['provider_usage'][name] = count
            logger.info(f"Initialized total_stores to {total_memories} from providers")
        else:
            logger.warning("No memories found in any provider during initialization")
            
    except Exception as e:
        logger.error(f"Failed to sync initial stats: {e}")
```

### Step 3: Add get_stats Method to Providers (PRIORITY 2)

Add to `PgVectorProvider` in `providers.py`:

```python
async def get_stats(self) -> dict[str, Any]:
    """Get provider statistics including total memory count."""
    try:
        async with self.connection_pool.acquire() as conn:
            # Get total count
            total_count = await conn.fetchval(
                f"SELECT COUNT(*) FROM {self.table_name}"
            )
            
            # Get count with embeddings
            with_embeddings = await conn.fetchval(
                f"SELECT COUNT(*) FROM {self.table_name} WHERE embedding IS NOT NULL"
            )
            
            # Get table size
            table_size = await conn.fetchval(f"""
                SELECT pg_size_pretty(pg_total_relation_size('{self.table_name}'))
            """)
            
            return {
                'total_memories': total_count,
                'memories_with_embeddings': with_embeddings,
                'memories_without_embeddings': total_count - with_embeddings,
                'table_size': table_size,
                'provider': self.name,
                'status': 'healthy'
            }
            
    except Exception as e:
        logger.error(f"Failed to get stats: {e}")
        return {
            'total_memories': 0,
            'error': str(e),
            'status': 'error'
        }
```

### Step 4: Fix Health Check Aggregation (PRIORITY 1)

Update the health check method to properly aggregate counts (already partially fixed, but ensure it's complete):

```python
async def health_check(self) -> dict[str, Any]:
    """Check health of all providers."""
    results = {}
    overall_healthy = True
    
    for name, provider in self.providers.items():
        try:
            if provider.enabled:
                health = await provider.health_check()
                results[name] = {
                    'status': 'healthy',
                    'details': health,
                    'primary': provider == self.primary_provider
                }
            else:
                results[name] = {'status': 'disabled'}
                
        except Exception as e:
            results[name] = {
                'status': 'unhealthy',
                'error': str(e),
                'primary': provider == self.primary_provider
            }
            if provider == self.primary_provider:
                overall_healthy = False
    
    # Calculate actual total memories from all providers
    actual_total_memories = 0
    for provider_name, provider_health in results.items():
        if provider_health.get('status') == 'healthy':
            details = provider_health.get('details', {})
            # Try multiple locations for the count
            count = 0
            if 'total_vectors' in details:
                count = details['total_vectors']
            elif 'details' in details and 'total_vectors' in details['details']:
                count = details['details']['total_vectors']
            elif 'total_memories' in details:
                count = details['total_memories']
            
            actual_total_memories += count
    
    # Always update stats with actual total
    if actual_total_memories > 0:
        self.stats['total_stores'] = actual_total_memories
    
    return {
        'status': 'healthy' if overall_healthy else 'degraded',
        'providers': results,
        'stats': self.stats,
        'cache_size': len(self.query_cache) if isinstance(self.query_cache, dict) else 0
    }
```

## Testing Strategy

### 1. **Local Testing**
```bash
# Start the service locally
cd /mnt/c/Users/Tyvon/core-nexus/python/memory_service
poetry run uvicorn src.memory_service.api:app --reload

# Test the fix
python fix_sync_issue.py http://localhost:8000

# Verify with diagnostic
python diagnose_sync_issue.py
```

### 2. **API Testing Script**
Create `test_sync_fix.py`:

```python
import asyncio
import httpx

async def test_sync_fix(base_url="http://localhost:8000"):
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("1. Checking initial health...")
        health = await client.get(f"{base_url}/health")
        print(f"   Total memories (before): {health.json()['total_memories']}")
        
        print("\n2. Refreshing stats...")
        refresh = await client.post(
            f"{base_url}/admin/refresh-stats",
            params={"admin_key": "refresh-stats-2025"}
        )
        if refresh.status_code == 200:
            data = refresh.json()
            print(f"   Old: {data['old_total_memories']}")
            print(f"   New: {data['new_total_memories']}")
        else:
            print(f"   Error: {refresh.status_code}")
        
        print("\n3. Checking health again...")
        health = await client.get(f"{base_url}/health")
        print(f"   Total memories (after): {health.json()['total_memories']}")
        
        print("\n4. Testing emergency endpoint...")
        emergency = await client.get(f"{base_url}/emergency/find-all-memories?limit=10")
        if emergency.status_code == 200:
            data = emergency.json()
            print(f"   Found: {data['total_memories_found']} memories")
        
        print("\n5. Testing regular query...")
        query = await client.post(
            f"{base_url}/memories/query",
            json={"query": "", "limit": 10}
        )
        if query.status_code == 200:
            data = query.json()
            print(f"   Query returned: {data['total_found']} memories")

if __name__ == "__main__":
    asyncio.run(test_sync_fix())
```

### 3. **Production Testing**
```bash
# Test on production (carefully)
python fix_sync_issue.py https://core-nexus-memory.onrender.com

# Monitor logs
curl https://core-nexus-memory.onrender.com/debug/logs?lines=50

# Check metrics
curl https://core-nexus-memory.onrender.com/memories/stats
```

## Prevention Measures

### 1. **Startup Health Check**
Add to lifespan startup:
```python
# After unified_store initialization
if unified_store:
    # Wait for initial sync
    await asyncio.sleep(3)
    
    # Verify stats are synced
    health = await unified_store.health_check()
    total = health['stats']['total_stores']
    if total == 0:
        logger.warning("Stats show 0 memories after initialization, forcing refresh...")
        await unified_store.refresh_stats()
```

### 2. **Periodic Stats Sync**
Add background task:
```python
async def periodic_stats_sync():
    """Sync stats every hour to prevent drift."""
    while True:
        try:
            await asyncio.sleep(3600)  # 1 hour
            if unified_store:
                await unified_store.refresh_stats()
                logger.info("Periodic stats sync completed")
        except Exception as e:
            logger.error(f"Periodic sync failed: {e}")

# Add to lifespan
asyncio.create_task(periodic_stats_sync())
```

### 3. **Monitoring Alerts**
Set up alerts for:
- Health endpoint returning 0 memories when DB has data
- Large discrepancies between provider counts
- Stats not updating after memory operations

### 4. **Database Constraints**
Add database trigger to track counts:
```sql
-- Create stats table
CREATE TABLE IF NOT EXISTS memory_stats (
    id SERIAL PRIMARY KEY,
    total_count INTEGER NOT NULL,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Trigger to update stats
CREATE OR REPLACE FUNCTION update_memory_stats()
RETURNS TRIGGER AS $$
BEGIN
    INSERT INTO memory_stats (total_count)
    SELECT COUNT(*) FROM vector_memories;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER memory_stats_trigger
AFTER INSERT OR DELETE ON vector_memories
FOR EACH STATEMENT
EXECUTE FUNCTION update_memory_stats();
```

## Timeline and Priority

### Immediate (0-2 hours)
1. **Deploy admin endpoints** - Critical for manual fix
2. **Fix health check aggregation** - Ensures accurate reporting
3. **Test and deploy to production** - Restore accurate stats

### Short-term (2-4 hours)
1. **Improve initial sync** - Prevent future occurrences
2. **Add provider get_stats methods** - Better stats collection
3. **Create monitoring dashboard** - Track stats drift

### Long-term (1-2 days)
1. **Implement periodic sync** - Automated prevention
2. **Add database triggers** - Source of truth for counts
3. **Set up alerting** - Proactive monitoring

## Code Snippets for Key Fixes

### 1. Quick Hot-Fix Script
Save as `emergency_fix.py`:
```python
#!/usr/bin/env python3
import os
import asyncio
import asyncpg

async def emergency_fix():
    # Direct DB connection
    conn = await asyncpg.connect(
        host=os.getenv("PGVECTOR_HOST"),
        port=int(os.getenv("PGVECTOR_PORT", "5432")),
        database=os.getenv("PGVECTOR_DATABASE"),
        user=os.getenv("PGVECTOR_USER"),
        password=os.getenv("PGVECTOR_PASSWORD")
    )
    
    # Get actual count
    count = await conn.fetchval("SELECT COUNT(*) FROM vector_memories")
    print(f"Actual memories in database: {count}")
    
    # TODO: Update application state via API
    await conn.close()

if __name__ == "__main__":
    asyncio.run(emergency_fix())
```

### 2. Deployment Commands
```bash
# Local testing
cd python/memory_service
poetry install
poetry run pytest tests/test_sync_fix.py
poetry run uvicorn src.memory_service.api:app --reload

# Deploy to Render
git add -A
git commit -m "fix: Add admin endpoints for stats synchronization"
git push origin main

# After deployment
curl -X POST "https://core-nexus-memory.onrender.com/admin/refresh-stats?admin_key=refresh-stats-2025"
```

## Rollback Plan

If the fix causes issues:

### 1. **Immediate Rollback**
```bash
# Revert to previous commit
git revert HEAD
git push origin main

# Render will auto-deploy previous version
```

### 2. **Data Safety**
- No data modifications are made
- Only stats counters are updated
- All changes are reversible

### 3. **Emergency Contacts**
- Monitor Render dashboard
- Check application logs
- Alert team if issues persist

## Success Criteria

The fix is successful when:
1. ✅ Health endpoint shows correct memory count (1,095+)
2. ✅ Stats endpoint matches database count
3. ✅ Query endpoint returns memories correctly
4. ✅ No performance degradation
5. ✅ Stats remain synchronized after new memory operations

## Conclusion

This comprehensive plan addresses the root cause of the data synchronization issue through multiple approaches:
1. Admin endpoints for immediate manual fixes
2. Automatic synchronization on startup
3. Periodic sync to prevent future drift
4. Emergency fallback endpoints for reliability

The fix is safe, reversible, and maintains backward compatibility while ensuring accurate reporting of system state.