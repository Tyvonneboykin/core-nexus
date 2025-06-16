#!/usr/bin/env python3
"""
Debug the table name issue and test direct queries.
"""
import asyncio
import httpx
import os

PRODUCTION_URL = "https://core-nexus-memory-service.onrender.com"

async def debug_table_issue():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("=== Debugging Core Nexus Table Issue ===\n")
        
        # 1. Check providers configuration
        print("1. Checking provider configuration...")
        try:
            response = await client.get(f"{PRODUCTION_URL}/providers")
            if response.status_code == 200:
                data = response.json()
                print(f"Primary provider: {data.get('primary_provider')}")
                for provider in data.get('providers', []):
                    print(f"\nProvider: {provider['name']}")
                    print(f"  Enabled: {provider['enabled']}")
                    print(f"  Stats: {provider.get('stats', {})}")
        except Exception as e:
            print(f"Error: {e}")
        
        # 2. Check debug environment
        print("\n2. Checking environment variables...")
        try:
            response = await client.get(f"{PRODUCTION_URL}/debug/env")
            if response.status_code == 200:
                data = response.json()
                pg_config = data.get('postgresql', {})
                print(f"PGVECTOR_HOST: {pg_config.get('PGVECTOR_HOST')}")
                print(f"PGVECTOR_DATABASE: {pg_config.get('PGVECTOR_DATABASE')}")
                print(f"Primary provider: {data.get('primary_provider')}")
        except Exception as e:
            print(f"Error: {e}")
        
        # 3. Test different query approaches
        print("\n3. Testing query approaches...")
        
        # Test empty query
        print("\n3a. Empty query test:")
        try:
            response = await client.post(
                f"{PRODUCTION_URL}/memories/query",
                json={"query": "", "limit": 5}
            )
            data = response.json()
            print(f"Total found: {data.get('total_found')}")
            print(f"Providers used: {data.get('providers_used')}")
        except Exception as e:
            print(f"Error: {e}")
        
        # Test with a simple word
        print("\n3b. Simple query test:")
        try:
            response = await client.post(
                f"{PRODUCTION_URL}/memories/query",
                json={"query": "test", "limit": 5}
            )
            data = response.json()
            print(f"Total found: {data.get('total_found')}")
        except Exception as e:
            print(f"Error: {e}")
        
        # Test GET endpoint
        print("\n3c. GET /memories test:")
        try:
            response = await client.get(f"{PRODUCTION_URL}/memories?limit=5")
            data = response.json()
            print(f"Total found: {data.get('total_found')}")
            print(f"Providers used: {data.get('providers_used')}")
        except Exception as e:
            print(f"Error: {e}")
        
        # 4. Check logs for errors
        print("\n4. Checking recent logs for table-related errors...")
        try:
            response = await client.get(f"{PRODUCTION_URL}/debug/logs?lines=20")
            if response.status_code == 200:
                data = response.json()
                logs = data.get('logs', [])
                table_errors = [log for log in logs if 'table' in log.get('message', '').lower() or 'vector_memories' in log.get('message', '')]
                if table_errors:
                    print("Found table-related errors:")
                    for log in table_errors[:5]:
                        print(f"  [{log['level']}] {log['message']}")
                else:
                    print("No table-related errors in recent logs")
        except Exception as e:
            print(f"Error: {e}")

if __name__ == "__main__":
    asyncio.run(debug_table_issue())