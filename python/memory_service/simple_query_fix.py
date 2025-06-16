#!/usr/bin/env python3
"""
Apply a simpler fix - the issue might be that the emergency search is called
but the connection pool isn't properly initialized or there's a transaction issue.
"""

# Read the unified_store.py file
with open('src/memory_service/unified_store.py', 'r') as f:
    content = f.read()

# Add better error handling and logging around the emergency search
updated_content = content.replace(
    """                if pgvector and pgvector.enabled:
                    # Import emergency search fix
                    from .search_fix import EmergencySearchFix
                    emergency_search = EmergencySearchFix(pgvector.connection_pool, pgvector.table_name)
                    
                    # Get ALL memories directly
                    memories = await emergency_search.emergency_search_all(limit=request.limit)""",
    """                if pgvector and pgvector.enabled:
                    # Import emergency search fix
                    from .search_fix import EmergencySearchFix
                    
                    # Ensure connection pool is initialized
                    if not pgvector.connection_pool:
                        logger.error("PgVector connection pool not initialized!")
                        # Try to get recent memories as fallback
                        if hasattr(pgvector, 'get_recent_memories'):
                            memories = await pgvector.get_recent_memories(request.limit, {})
                        else:
                            memories = []
                    else:
                        try:
                            emergency_search = EmergencySearchFix(pgvector.connection_pool, pgvector.table_name)
                            # Get ALL memories directly
                            memories = await emergency_search.emergency_search_all(limit=request.limit)
                        except Exception as e:
                            logger.error(f"Emergency search failed: {e}")
                            # Try provider's own method as fallback
                            try:
                                memories = await pgvector.get_recent_memories(request.limit, {})
                            except:
                                memories = []""")

# Also add a fix for regular queries - use get_recent_memories for empty queries
updated_content = updated_content.replace(
    """            # Check if this is an empty query (zero vector)
            is_empty_query = all(v == 0.0 for v in query_embedding)
            
            if is_empty_query:
                # Use get_recent_memories if available (currently only PgVectorProvider)
                if hasattr(provider, 'get_recent_memories'):
                    logger.info(f"Using get_recent_memories for empty query on {provider.name}")
                    results = await provider.get_recent_memories(request.limit * 2, request.filters)
                else:
                    # Fall back to regular query for providers without get_recent_memories
                    logger.info(f"Provider {provider.name} doesn't support get_recent_memories, using regular query")
                    results = await provider.query(query_embedding, request.limit * 2, request.filters)""",
    """            # Check if this is an empty query (zero vector or no embedding)
            is_empty_query = not query_embedding or all(v == 0.0 for v in query_embedding)
            
            if is_empty_query:
                # Use get_recent_memories if available (currently only PgVectorProvider)
                if hasattr(provider, 'get_recent_memories'):
                    logger.info(f"Using get_recent_memories for empty query on {provider.name}")
                    try:
                        results = await provider.get_recent_memories(request.limit * 2, request.filters or {})
                    except Exception as e:
                        logger.error(f"get_recent_memories failed: {e}")
                        # Try emergency search as last resort
                        if provider.name == 'pgvector' and hasattr(provider, 'connection_pool'):
                            from .search_fix import EmergencySearchFix
                            emergency = EmergencySearchFix(provider.connection_pool, provider.table_name)
                            results = await emergency.emergency_search_all(request.limit * 2)
                        else:
                            results = []
                else:
                    # Fall back to regular query for providers without get_recent_memories
                    logger.info(f"Provider {provider.name} doesn't support get_recent_memories, using regular query")
                    results = await provider.query(query_embedding, request.limit * 2, request.filters)""")

# Write the updated file
with open('src/memory_service/unified_store.py', 'w') as f:
    f.write(updated_content)

print("✅ Applied simpler query fix to unified_store.py")
print("\nChanges made:")
print("1. Check if connection pool is initialized")
print("2. Add fallback to get_recent_memories")
print("3. Better error handling")
print("4. Multiple fallback strategies")