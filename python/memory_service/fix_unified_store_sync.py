#!/usr/bin/env python3
"""
Script to add the refresh_stats method to UnifiedVectorStore.
This enables manual stats synchronization.
"""

# Read the current unified_store.py
with open('src/memory_service/unified_store.py', 'r') as f:
    content = f.read()

# Find where to insert (after _sync_initial_stats method)
insert_point = content.find('async def _sync_initial_stats(self):')
if insert_point == -1:
    print("Could not find _sync_initial_stats method!")
    exit(1)

# Find the end of the method
method_end = content.find('\n    async def', insert_point + 1)
if method_end == -1:
    method_end = content.find('\n    def', insert_point + 1)

# Add refresh_stats method
refresh_method = '''
    async def refresh_stats(self) -> int:
        """
        Manually refresh stats from all providers.
        Returns the new total count.
        """
        try:
            logger.info("Refreshing stats from all providers...")
            
            total_memories = 0
            provider_counts = {}
            
            for name, provider in self.providers.items():
                if provider.enabled:
                    try:
                        count = 0
                        
                        # Try to get count from health check
                        health = await provider.health_check()
                        if isinstance(health, dict):
                            # Check various possible locations for the count
                            if 'total_vectors' in health:
                                count = health['total_vectors']
                            elif 'details' in health and 'total_vectors' in health['details']:
                                count = health['details']['total_vectors']
                            elif 'total_memories' in health:
                                count = health['total_memories']
                        
                        # Special handling for pgvector
                        if count == 0 and name == 'pgvector' and hasattr(provider, 'connection_pool'):
                            async with provider.connection_pool.acquire() as conn:
                                count = await conn.fetchval("SELECT COUNT(*) FROM vector_memories")
                        
                        if count > 0:
                            total_memories += count
                            provider_counts[name] = count
                            logger.info(f"Provider {name} has {count} memories")
                            
                    except Exception as e:
                        logger.warning(f"Failed to get count from {name}: {e}")
                        provider_counts[name] = 0
            
            # Update stats
            old_total = self.stats.get('total_stores', 0)
            self.stats['total_stores'] = total_memories
            
            # Update provider usage
            for name, count in provider_counts.items():
                if count > 0:
                    self.stats['provider_usage'][name] = count
            
            logger.info(f"Stats refreshed: {old_total} -> {total_memories} total memories")
            return total_memories
            
        except Exception as e:
            logger.error(f"Failed to refresh stats: {e}")
            raise

'''

# Insert the method
new_content = content[:method_end] + refresh_method + '\n' + content[method_end:]

# Write back
with open('src/memory_service/unified_store.py', 'w') as f:
    f.write(new_content)

print("✅ refresh_stats method added to UnifiedVectorStore!")
print("This enables the admin endpoint to manually sync stats.")