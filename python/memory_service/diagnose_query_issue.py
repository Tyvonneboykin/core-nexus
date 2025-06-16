#!/usr/bin/env python3
"""
Diagnostic script to identify why queries return 0 memories
despite health endpoint showing 1096.
"""

import asyncio
import asyncpg
import os
import logging
from datetime import datetime

# Set up logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def diagnose_database():
    """Run comprehensive diagnostics on the database."""
    
    # Database connection parameters
    conn_params = {
        'host': os.getenv("PGVECTOR_HOST", "dpg-d12n0np5pdvs73ctmm40-a.oregon-postgres.render.com"),
        'port': int(os.getenv("PGVECTOR_PORT", "5432")),
        'database': os.getenv("PGVECTOR_DATABASE", "nexus_memory_db"),
        'user': os.getenv("PGVECTOR_USER", "nexus_memory_db_user"),
        'password': os.getenv("PGPASSWORD") or os.getenv("PGVECTOR_PASSWORD"),
    }
    
    if not conn_params['password']:
        logger.error("No password found in PGPASSWORD or PGVECTOR_PASSWORD environment variables")
        return
    
    try:
        # Create connection
        conn = await asyncpg.connect(**conn_params)
        logger.info("Successfully connected to database")
        
        # 1. Check table existence
        tables = await conn.fetch("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename IN ('memories', 'vector_memories')
        """)
        logger.info(f"Found tables: {[t['tablename'] for t in tables]}")
        
        # 2. Count memories in each table
        for table in tables:
            table_name = table['tablename']
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
            logger.info(f"Table '{table_name}' has {count} rows")
            
            # Get sample data
            if count > 0:
                sample = await conn.fetch(f"""
                    SELECT id, SUBSTRING(content, 1, 100) as content_preview,
                           CASE WHEN embedding IS NULL THEN 'NULL' ELSE 'EXISTS' END as embedding_status,
                           created_at
                    FROM {table_name}
                    ORDER BY created_at DESC
                    LIMIT 5
                """)
                logger.info(f"Sample data from {table_name}:")
                for row in sample:
                    logger.info(f"  ID: {row['id']}, Embedding: {row['embedding_status']}, "
                              f"Created: {row['created_at']}, Content: {row['content_preview']}...")
        
        # 3. Check for NULL embeddings
        null_embedding_count = await conn.fetchval("""
            SELECT COUNT(*) 
            FROM vector_memories 
            WHERE embedding IS NULL
        """)
        logger.info(f"Memories with NULL embeddings: {null_embedding_count}")
        
        # 4. Check partitioning
        partitions = await conn.fetch("""
            SELECT 
                inhrelid::regclass AS partition_name,
                pg_get_expr(relpartbound, inhrelid) AS partition_range
            FROM pg_inherits
            WHERE inhparent = 'vector_memories'::regclass
            ORDER BY partition_name
        """)
        if partitions:
            logger.info(f"Found {len(partitions)} partitions:")
            for p in partitions[:5]:  # Show first 5
                logger.info(f"  {p['partition_name']}: {p['partition_range']}")
        
        # 5. Check current date/time to understand partitioning
        current_time = await conn.fetchval("SELECT NOW()")
        logger.info(f"Database current time: {current_time}")
        
        # 6. Check memories in current month's partition
        current_partition = f"vector_memories_{current_time.year}_{current_time.month:02d}"
        try:
            partition_count = await conn.fetchval(f"SELECT COUNT(*) FROM {current_partition}")
            logger.info(f"Current partition '{current_partition}' has {partition_count} memories")
        except Exception as e:
            logger.warning(f"Could not check partition {current_partition}: {e}")
        
        # 7. Test direct query that emergency search uses
        emergency_query_rows = await conn.fetch("""
            SELECT 
                id, 
                content, 
                metadata, 
                importance_score,
                created_at
            FROM vector_memories
            ORDER BY created_at DESC
            LIMIT 10
        """)
        logger.info(f"Emergency query returned {len(emergency_query_rows)} rows")
        
        # 8. Check if there's a connection pool issue
        pool_test = await conn.fetchval("SELECT 1")
        logger.info(f"Connection pool test: {pool_test}")
        
        # 9. Check for any locks on the table
        locks = await conn.fetch("""
            SELECT 
                pid,
                mode,
                granted,
                relation::regclass
            FROM pg_locks
            WHERE relation = 'vector_memories'::regclass
        """)
        if locks:
            logger.info(f"Found {len(locks)} locks on vector_memories table")
            for lock in locks:
                logger.info(f"  PID: {lock['pid']}, Mode: {lock['mode']}, Granted: {lock['granted']}")
        
        # 10. Check table statistics
        stats = await conn.fetchrow("""
            SELECT 
                n_live_tup as live_rows,
                n_dead_tup as dead_rows,
                last_vacuum,
                last_autovacuum,
                last_analyze,
                last_autoanalyze
            FROM pg_stat_user_tables
            WHERE relname = 'vector_memories'
        """)
        if stats:
            logger.info(f"Table statistics:")
            logger.info(f"  Live rows: {stats['live_rows']}")
            logger.info(f"  Dead rows: {stats['dead_rows']}")
            logger.info(f"  Last vacuum: {stats['last_vacuum']}")
            logger.info(f"  Last analyze: {stats['last_analyze']}")
        
        await conn.close()
        logger.info("Diagnosis completed successfully")
        
    except Exception as e:
        logger.error(f"Error during diagnosis: {e}")
        import traceback
        traceback.print_exc()


async def test_api_endpoints():
    """Test the API endpoints directly."""
    import httpx
    
    api_url = os.getenv("API_URL", "http://localhost:8000")
    
    async with httpx.AsyncClient() as client:
        # Test health endpoint
        try:
            response = await client.get(f"{api_url}/health")
            if response.status_code == 200:
                health_data = response.json()
                logger.info(f"Health endpoint response: {health_data}")
                
                # Extract memory count from health data
                if 'stats' in health_data:
                    logger.info(f"Stats from health: {health_data['stats']}")
                if 'providers' in health_data:
                    for provider, info in health_data['providers'].items():
                        if info.get('status') == 'healthy' and 'details' in info:
                            logger.info(f"Provider {provider}: {info['details']}")
        except Exception as e:
            logger.error(f"Failed to call health endpoint: {e}")
        
        # Test query endpoint with empty query
        try:
            response = await client.post(
                f"{api_url}/query",
                json={
                    "query": "",
                    "limit": 10
                }
            )
            if response.status_code == 200:
                query_data = response.json()
                logger.info(f"Empty query returned {query_data.get('total_found', 0)} memories")
                logger.info(f"Providers used: {query_data.get('providers_used', [])}")
                if query_data.get('memories'):
                    logger.info(f"First memory: {query_data['memories'][0]}")
            else:
                logger.error(f"Query endpoint returned status {response.status_code}: {response.text}")
        except Exception as e:
            logger.error(f"Failed to call query endpoint: {e}")


async def main():
    """Run all diagnostics."""
    logger.info("Starting Core Nexus query diagnostics...")
    
    # Run database diagnostics
    await diagnose_database()
    
    # Test API endpoints if running
    if os.getenv("SKIP_API_TEST") != "true":
        logger.info("\nTesting API endpoints...")
        await test_api_endpoints()
    
    logger.info("\nDiagnostics completed!")


if __name__ == "__main__":
    asyncio.run(main())