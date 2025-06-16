#!/usr/bin/env python3
"""
Quick script to check which tables exist in the database.
"""

import asyncio
import asyncpg
import os
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def check_tables():
    """Check which memory-related tables exist."""
    
    conn_params = {
        'host': os.getenv("PGVECTOR_HOST", "dpg-d12n0np5pdvs73ctmm40-a.oregon-postgres.render.com"),
        'port': int(os.getenv("PGVECTOR_PORT", "5432")),
        'database': os.getenv("PGVECTOR_DATABASE", "nexus_memory_db"),
        'user': os.getenv("PGVECTOR_USER", "nexus_memory_db_user"),
        'password': os.getenv("PGPASSWORD") or os.getenv("PGVECTOR_PASSWORD"),
    }
    
    if not conn_params['password']:
        logger.error("No password found in PGPASSWORD or PGVECTOR_PASSWORD")
        return
    
    try:
        conn = await asyncpg.connect(**conn_params)
        
        # Check all tables
        tables = await conn.fetch("""
            SELECT tablename, tableowner
            FROM pg_tables 
            WHERE schemaname = 'public' 
            AND (tablename LIKE '%memor%' OR tablename = 'memories')
            ORDER BY tablename
        """)
        
        logger.info(f"Found {len(tables)} memory-related tables:")
        for table in tables:
            logger.info(f"  - {table['tablename']} (owner: {table['tableowner']})")
            
            # Get row count for each table
            try:
                count = await conn.fetchval(f"SELECT COUNT(*) FROM {table['tablename']}")
                logger.info(f"    Rows: {count}")
            except Exception as e:
                logger.error(f"    Error counting rows: {e}")
        
        # Check if vector_memories is partitioned
        partitions = await conn.fetch("""
            SELECT 
                inhrelid::regclass AS partition_name
            FROM pg_inherits
            WHERE inhparent = 'vector_memories'::regclass
            LIMIT 5
        """)
        
        if partitions:
            logger.info(f"\nvector_memories is PARTITIONED with {len(partitions)} partitions")
        else:
            logger.info("\nvector_memories is NOT partitioned")
        
        # Check indexes on vector_memories
        indexes = await conn.fetch("""
            SELECT indexname, indexdef
            FROM pg_indexes
            WHERE tablename = 'vector_memories'
            ORDER BY indexname
        """)
        
        logger.info(f"\nIndexes on vector_memories ({len(indexes)} total):")
        for idx in indexes[:5]:  # Show first 5
            logger.info(f"  - {idx['indexname']}")
        
        await conn.close()
        
    except Exception as e:
        logger.error(f"Error: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(check_tables())