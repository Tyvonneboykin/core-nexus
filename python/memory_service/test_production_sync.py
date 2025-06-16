#!/usr/bin/env python3
"""
Test the data sync fix on production after deployment.
Wait for Render to deploy then run this script.
"""
import asyncio
import httpx
import time

PRODUCTION_URL = "https://core-nexus-memory.onrender.com"
ADMIN_KEY = "refresh-stats-2025"

async def test_production_sync():
    async with httpx.AsyncClient(timeout=30.0) as client:
        print("=== Testing Core Nexus Data Sync Fix ===\n")
        
        # 1. Check current health status
        print("1. Checking current health status...")
        try:
            health = await client.get(f"{PRODUCTION_URL}/health")
            if health.status_code == 200:
                data = health.json()
                print(f"   Status: {data['status']}")
                print(f"   Total memories (before fix): {data['total_memories']}")
                print(f"   Uptime: {data.get('uptime_seconds', 0):.1f} seconds")
            else:
                print(f"   Error: HTTP {health.status_code}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # 2. Wait a moment for deployment to settle
        print("\n2. Waiting for deployment to stabilize...")
        await asyncio.sleep(5)
        
        # 3. Call refresh stats endpoint
        print("\n3. Calling refresh stats endpoint...")
        try:
            refresh = await client.post(
                f"{PRODUCTION_URL}/admin/refresh-stats",
                params={"admin_key": ADMIN_KEY}
            )
            if refresh.status_code == 200:
                data = refresh.json()
                print(f"   ✅ Success!")
                print(f"   Old total: {data['old_total_memories']}")
                print(f"   New total: {data['new_total_memories']}")
                print(f"   Difference: {data['difference']}")
                print(f"   Message: {data['message']}")
                
                # Show provider breakdown
                if 'providers' in data:
                    print(f"\n   Provider breakdown:")
                    for provider, count in data['providers'].items():
                        print(f"     - {provider}: {count} memories")
            else:
                print(f"   ❌ Error: HTTP {refresh.status_code}")
                print(f"   Response: {refresh.text}")
        except Exception as e:
            print(f"   ❌ Error: {e}")
        
        # 4. Check health again
        print("\n4. Verifying health endpoint after refresh...")
        try:
            health = await client.get(f"{PRODUCTION_URL}/health")
            if health.status_code == 200:
                data = health.json()
                print(f"   Total memories (after fix): {data['total_memories']}")
                
                # Check provider details
                if 'providers' in data:
                    print(f"\n   Provider health:")
                    for provider, info in data['providers'].items():
                        status = info.get('status', 'unknown')
                        primary = info.get('primary', False)
                        print(f"     - {provider}: {status} {'(primary)' if primary else ''}")
            else:
                print(f"   Error: HTTP {health.status_code}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # 5. Test emergency endpoint
        print("\n5. Testing emergency memory retrieval...")
        try:
            emergency = await client.get(f"{PRODUCTION_URL}/emergency/find-all-memories?limit=5")
            if emergency.status_code == 200:
                data = emergency.json()
                print(f"   Total found: {data['total_memories_found']} memories")
                print(f"   Preview of first few memories:")
                for i, mem in enumerate(data.get('memories', [])[:3]):
                    print(f"     {i+1}. {mem['content_preview'][:50]}...")
            else:
                print(f"   Error: HTTP {emergency.status_code}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # 6. Test regular query
        print("\n6. Testing regular memory query...")
        try:
            query = await client.post(
                f"{PRODUCTION_URL}/memories/query",
                json={"query": "", "limit": 5}
            )
            if query.status_code == 200:
                data = query.json()
                print(f"   Query returned: {data['total_found']} memories")
                print(f"   Actually returned: {len(data['memories'])} memories")
                if data.get('trust_metrics'):
                    print(f"   Confidence score: {data['trust_metrics']['confidence_score']}")
            else:
                print(f"   Error: HTTP {query.status_code}")
        except Exception as e:
            print(f"   Error: {e}")
        
        # 7. Get comprehensive stats
        print("\n7. Getting comprehensive memory stats...")
        try:
            stats = await client.get(f"{PRODUCTION_URL}/memories/stats")
            if stats.status_code == 200:
                data = stats.json()
                print(f"   Total memories: {data['total_memories']}")
                print(f"   By provider:")
                for provider, count in data.get('memories_by_provider', {}).items():
                    print(f"     - {provider}: {count}")
                print(f"   Avg query time: {data.get('avg_query_time_ms', 0):.1f}ms")
            else:
                print(f"   Error: HTTP {stats.status_code}")
        except Exception as e:
            print(f"   Error: {e}")
        
        print("\n=== Test Complete ===")
        print("\nSummary:")
        print("- If the refresh was successful, you should see 1,095+ memories")
        print("- The health endpoint should now report accurate counts")
        print("- Memory queries should return actual data")
        print("\nNext steps:")
        print("1. Monitor the health endpoint periodically")
        print("2. Check if stats remain synchronized")
        print("3. Test memory creation to ensure counters update properly")

async def wait_for_deployment():
    """Wait for Render deployment to complete."""
    print("Waiting for Render deployment to complete...")
    print("This typically takes 2-3 minutes after pushing to GitHub.")
    print("Checking deployment status...\n")
    
    async with httpx.AsyncClient(timeout=10.0) as client:
        for i in range(30):  # Check for up to 5 minutes
            try:
                # Check if the new endpoint exists
                response = await client.post(
                    f"{PRODUCTION_URL}/admin/refresh-stats",
                    params={"admin_key": "wrong-key"}  # Use wrong key to test endpoint exists
                )
                if response.status_code == 403:  # 403 means endpoint exists but wrong key
                    print("\n✅ Deployment complete! New endpoints are available.")
                    return True
                elif response.status_code == 404:
                    print(f"\r⏳ Waiting for deployment... ({i*10}/300 seconds)", end="")
                else:
                    print(f"\nUnexpected response: {response.status_code}")
            except Exception:
                print(f"\r⏳ Service not responding yet... ({i*10}/300 seconds)", end="")
            
            await asyncio.sleep(10)
    
    print("\n\n⚠️  Deployment might still be in progress.")
    print("You can check: https://dashboard.render.com")
    return False

async def main():
    # Wait for deployment
    deployed = await wait_for_deployment()
    
    if deployed:
        print("\nStarting production sync test...\n")
        await asyncio.sleep(2)
        await test_production_sync()
    else:
        print("\nDeployment check timed out. You can run this script again later.")
        print("Or proceed with testing anyway? (y/n): ", end="")
        if input().lower() == 'y':
            await test_production_sync()

if __name__ == "__main__":
    asyncio.run(main())