#!/usr/bin/env python3
"""
Test direct database queries to verify the issue.
"""

import asyncio
import asyncpg
import os
import logging
import sys

# Add the src directory to the path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from memory_service.providers import PgVectorProvider
from memory_service.models import ProviderConfig
from memory_service.search_fix import EmergencySearchFix

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def test_direct_db():
    """Test direct database connection."""
    conn_params = {
        'host': os.getenv("PGVECTOR_HOST", "dpg-d12n0np5pdvs73ctmm40-a.oregon-postgres.render.com"),
        'port': int(os.getenv("PGVECTOR_PORT", "5432")),
        'database': os.getenv("PGVECTOR_DATABASE", "nexus_memory_db"),
        'user': os.getenv("PGVECTOR_USER", "nexus_memory_db_user"),
        'password': os.getenv("PGPASSWORD") or os.getenv("PGVECTOR_PASSWORD"),
    }
    
    if not conn_params['password']:
        logger.error("No password found")
        return
    
    conn = await asyncpg.connect(**conn_params)
    
    # Test 1: Count memories directly
    count = await conn.fetchval("SELECT COUNT(*) FROM vector_memories")
    logger.info(f"Direct count from vector_memories: {count}")
    
    # Test 2: Get a few samples
    samples = await conn.fetch("""
        SELECT id, SUBSTRING(content, 1, 100) as content, created_at 
        FROM vector_memories 
        LIMIT 5
    """)
    logger.info(f"Sample memories: {len(samples)}")
    for s in samples:
        logger.info(f"  {s['id']}: {s['content'][:50]}...")
    
    await conn.close()


async def test_provider():
    """Test using the PgVectorProvider."""
    config = ProviderConfig(
        name="pgvector",
        enabled=True,
        primary=True,
        config={
            "host": os.getenv("PGVECTOR_HOST", "dpg-d12n0np5pdvs73ctmm40-a.oregon-postgres.render.com"),
            "port": int(os.getenv("PGVECTOR_PORT", "5432")),
            "database": os.getenv("PGVECTOR_DATABASE", "nexus_memory_db"),
            "user": os.getenv("PGVECTOR_USER", "nexus_memory_db_user"),
            "password": os.getenv("PGPASSWORD") or os.getenv("PGVECTOR_PASSWORD"),
            "table_name": "vector_memories",
            "embedding_dim": 1536
        }
    )
    
    provider = PgVectorProvider(config)
    
    # Wait for connection pool to initialize
    await asyncio.sleep(2)
    
    # Test 1: Health check
    health = await provider.health_check()
    logger.info(f"Provider health: {health}")
    
    # Test 2: Get recent memories
    memories = await provider.get_recent_memories(limit=10)
    logger.info(f"Recent memories: {len(memories)}")
    for m in memories[:3]:
        logger.info(f"  {m.id}: {m.content[:50]}...")
    
    # Test 3: Emergency search
    emergency = EmergencySearchFix(provider.connection_pool, provider.table_name)
    emergency_memories = await emergency.emergency_search_all(limit=10)
    logger.info(f"Emergency search returned: {len(emergency_memories)} memories")


async def test_api():
    """Test the API directly."""
    import httpx
    
    api_url = os.getenv("API_URL", "http://localhost:8000")
    
    async with httpx.AsyncClient() as client:
        # Test empty query
        response = await client.post(
            f"{api_url}/query",
            json={"query": "", "limit": 10}
        )
        
        if response.status_code == 200:
            data = response.json()
            logger.info(f"API empty query returned: {data.get('total_found', 0)} memories")
            logger.info(f"Providers used: {data.get('providers_used', [])}")
            if data.get('memories'):
                logger.info(f"First memory: {data['memories'][0].get('content', '')[:100]}...")
        else:
            logger.error(f"API error: {response.status_code} - {response.text}")


async def main():
    """Run all tests."""
    logger.info("Testing Core Nexus Memory Service queries...")
    
    # Test 1: Direct database
    logger.info("\n=== Testing Direct Database ===")
    await test_direct_db()
    
    # Test 2: Provider
    logger.info("\n=== Testing Provider ===")
    await test_provider()
    
    # Test 3: API (if available)
    if os.getenv("SKIP_API_TEST") != "true":
        logger.info("\n=== Testing API ===")
        await test_api()


if __name__ == "__main__":
    asyncio.run(main())