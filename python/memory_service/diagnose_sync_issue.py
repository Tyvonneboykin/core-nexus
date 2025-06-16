#!/usr/bin/env python3
"""
Diagnostic script to investigate Core Nexus data synchronization issues.

This script helps identify why there's a mismatch between:
- PgVector reporting 1,095 memories
- Health endpoint reporting 0 memories
- Inconsistency between providers
"""

import asyncio
import os
import asyncpg
from datetime import datetime
import json

# Import dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


async def check_pgvector_directly():
    """Check PgVector database directly."""
    print("\n=== CHECKING PGVECTOR DIRECTLY ===")
    
    # Get connection parameters
    host = os.getenv("PGVECTOR_HOST", "dpg-d12n0np5pdvs73ctmm40-a")
    port = int(os.getenv("PGVECTOR_PORT", "5432"))
    database = os.getenv("PGVECTOR_DATABASE", "nexus_memory_db")
    user = os.getenv("PGVECTOR_USER", "nexus_memory_db_user")
    password = os.getenv("PGVECTOR_PASSWORD") or os.getenv("PGPASSWORD")
    
    if not password:
        print("ERROR: No PostgreSQL password found in environment")
        return None
    
    conn_str = f"postgresql://{user}:{password}@{host}:{port}/{database}"
    
    try:
        conn = await asyncpg.connect(conn_str)
        
        # Check tables
        tables = await conn.fetch("""
            SELECT tablename 
            FROM pg_tables 
            WHERE schemaname = 'public' 
            AND tablename LIKE '%memor%'
            ORDER BY tablename
        """)
        
        print(f"\nMemory-related tables found:")
        for table in tables:
            print(f"  - {table['tablename']}")
        
        # Check each table
        results = {}
        for table in tables:
            table_name = table['tablename']
            
            # Get count
            count = await conn.fetchval(f"SELECT COUNT(*) FROM {table_name}")
            
            # Get sample row
            sample = await conn.fetchrow(f"SELECT * FROM {table_name} LIMIT 1")
            
            # Get columns
            columns = await conn.fetch(f"""
                SELECT column_name, data_type 
                FROM information_schema.columns 
                WHERE table_name = '{table_name}'
                ORDER BY ordinal_position
            """)
            
            results[table_name] = {
                'count': count,
                'columns': [f"{col['column_name']} ({col['data_type']})" for col in columns],
                'has_sample': sample is not None
            }
            
            print(f"\n{table_name}:")
            print(f"  Count: {count}")
            print(f"  Columns: {len(columns)}")
            if count > 0:
                print(f"  Sample ID: {sample['id'] if sample and 'id' in sample else 'N/A'}")
        
        # Check specific vector_memories table
        if 'vector_memories' in [t['tablename'] for t in tables]:
            print("\n=== VECTOR_MEMORIES DETAILED CHECK ===")
            
            # Count by presence of embeddings
            with_embeddings = await conn.fetchval(
                "SELECT COUNT(*) FROM vector_memories WHERE embedding IS NOT NULL"
            )
            without_embeddings = await conn.fetchval(
                "SELECT COUNT(*) FROM vector_memories WHERE embedding IS NULL"
            )
            
            print(f"Memories with embeddings: {with_embeddings}")
            print(f"Memories without embeddings: {without_embeddings}")
            
            # Check recent memories
            recent = await conn.fetch("""
                SELECT id, created_at, 
                       LENGTH(content) as content_length,
                       embedding IS NOT NULL as has_embedding
                FROM vector_memories 
                ORDER BY created_at DESC 
                LIMIT 5
            """)
            
            print("\nMost recent memories:")
            for mem in recent:
                print(f"  - {mem['id']} | {mem['created_at']} | "
                      f"Content: {mem['content_length']} chars | "
                      f"Embedding: {'Yes' if mem['has_embedding'] else 'No'}")
        
        await conn.close()
        return results
        
    except Exception as e:
        print(f"ERROR connecting to PgVector: {e}")
        return None


async def check_via_api():
    """Check via the API endpoints."""
    print("\n=== CHECKING VIA API ===")
    
    import httpx
    
    base_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # Check health endpoint
            print("\n1. Health endpoint:")
            health_resp = await client.get(f"{base_url}/health")
            if health_resp.status_code == 200:
                health_data = health_resp.json()
                print(f"   Status: {health_data['status']}")
                print(f"   Total memories: {health_data['total_memories']}")
                for provider, info in health_data['providers'].items():
                    print(f"   {provider}: {info['status']}")
                    if 'details' in info:
                        details = info['details']
                        if 'total_vectors' in details:
                            print(f"     - total_vectors: {details['total_vectors']}")
            else:
                print(f"   ERROR: Status code {health_resp.status_code}")
            
            # Check stats endpoint
            print("\n2. Stats endpoint:")
            stats_resp = await client.get(f"{base_url}/memories/stats")
            if stats_resp.status_code == 200:
                stats = stats_resp.json()
                print(f"   Total memories: {stats['total_memories']}")
                print(f"   By provider:")
                for provider, count in stats['memories_by_provider'].items():
                    print(f"     - {provider}: {count}")
            else:
                print(f"   ERROR: Status code {stats_resp.status_code}")
            
            # Check providers endpoint
            print("\n3. Providers endpoint:")
            providers_resp = await client.get(f"{base_url}/providers")
            if providers_resp.status_code == 200:
                providers = providers_resp.json()
                for provider in providers['providers']:
                    print(f"   {provider['name']}:")
                    print(f"     - Enabled: {provider['enabled']}")
                    print(f"     - Primary: {provider['primary']}")
                    if 'stats' in provider:
                        stats = provider['stats']
                        if 'total_memories' in stats:
                            print(f"     - Total memories: {stats['total_memories']}")
            else:
                print(f"   ERROR: Status code {providers_resp.status_code}")
            
            # Try emergency endpoint
            print("\n4. Emergency find-all endpoint:")
            emergency_resp = await client.get(f"{base_url}/emergency/find-all-memories")
            if emergency_resp.status_code == 200:
                emergency_data = emergency_resp.json()
                print(f"   Total found: {emergency_data['total_memories_found']}")
                if 'diagnostics' in emergency_data:
                    diag = emergency_data['diagnostics']
                    print(f"   Diagnostics:")
                    for key, value in diag.items():
                        print(f"     - {key}: {value}")
            else:
                print(f"   ERROR: Status code {emergency_resp.status_code}")
                
        except Exception as e:
            print(f"ERROR calling API: {e}")


async def check_chromadb():
    """Check ChromaDB directly."""
    print("\n=== CHECKING CHROMADB ===")
    
    try:
        import chromadb
        from chromadb.config import Settings
        
        # Initialize ChromaDB
        persist_dir = "./memory_service_chroma"
        client = chromadb.PersistentClient(
            path=persist_dir,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # List collections
        collections = client.list_collections()
        print(f"\nCollections found: {len(collections)}")
        
        for collection in collections:
            print(f"\n{collection.name}:")
            count = collection.count()
            print(f"  Count: {count}")
            
            # Get sample
            if count > 0:
                sample = collection.get(limit=1)
                if sample['ids']:
                    print(f"  Sample ID: {sample['ids'][0]}")
                    
    except ImportError:
        print("ChromaDB not installed")
    except Exception as e:
        print(f"ERROR checking ChromaDB: {e}")


async def suggest_fixes():
    """Suggest fixes based on findings."""
    print("\n=== SUGGESTED FIXES ===")
    
    print("""
1. **Refresh Stats Manually:**
   ```bash
   curl -X POST "http://localhost:8000/admin/refresh-stats?admin_key=refresh-stats-2025"
   ```

2. **Check for Table Name Mismatch:**
   - The code might be looking at wrong table
   - Check if using 'memories' vs 'vector_memories'

3. **Initialize Missing Indexes:**
   ```bash
   curl -X POST "http://localhost:8000/admin/init-database?admin_key=emergency-fix-2024"
   ```

4. **Clear Cache:**
   ```bash
   curl -X DELETE "http://localhost:8000/memories/cache"
   ```

5. **Check Environment Variables:**
   - Ensure PGVECTOR_* vars are set correctly
   - Check if connecting to right database

6. **Force Sync Between Providers:**
   - ChromaDB might have different data than PgVector
   - Consider running deduplication/sync script
""")


async def main():
    """Run all diagnostic checks."""
    print("Core Nexus Data Synchronization Diagnostic")
    print("=" * 50)
    print(f"Started at: {datetime.now().isoformat()}")
    
    # Check database directly
    db_results = await check_pgvector_directly()
    
    # Check via API
    await check_via_api()
    
    # Check ChromaDB
    await check_chromadb()
    
    # Suggest fixes
    await suggest_fixes()
    
    print("\n" + "=" * 50)
    print("Diagnostic complete!")
    
    # Summary
    if db_results:
        print("\n=== SUMMARY ===")
        for table, info in db_results.items():
            print(f"{table}: {info['count']} records")


if __name__ == "__main__":
    asyncio.run(main())