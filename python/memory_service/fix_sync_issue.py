#!/usr/bin/env python3
"""
Fix script for Core Nexus data synchronization issue.

This script fixes the mismatch between actual data and reported stats.
"""

import asyncio
import os
import sys
import httpx
from datetime import datetime

# Import dotenv if available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


async def fix_via_api(base_url: str = "http://localhost:8000"):
    """Fix the synchronization issue via API calls."""
    
    print(f"Connecting to API at: {base_url}")
    admin_key = os.getenv("ADMIN_KEY", "refresh-stats-2025")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        # Step 1: Check current status
        print("\n1. Checking current status...")
        try:
            health_resp = await client.get(f"{base_url}/health")
            if health_resp.status_code == 200:
                health_data = health_resp.json()
                print(f"   Current total_memories: {health_data['total_memories']}")
            else:
                print(f"   WARNING: Health check returned {health_resp.status_code}")
        except Exception as e:
            print(f"   ERROR: {e}")
        
        # Step 2: Clear cache
        print("\n2. Clearing query cache...")
        try:
            cache_resp = await client.delete(f"{base_url}/memories/cache")
            if cache_resp.status_code == 200:
                cache_data = cache_resp.json()
                print(f"   Cleared {cache_data['cache_size_before']} cached queries")
            else:
                print(f"   WARNING: Cache clear returned {cache_resp.status_code}")
        except Exception as e:
            print(f"   ERROR: {e}")
        
        # Step 3: Refresh stats
        print("\n3. Refreshing stats from providers...")
        try:
            refresh_resp = await client.post(
                f"{base_url}/admin/refresh-stats",
                params={"admin_key": admin_key}
            )
            if refresh_resp.status_code == 200:
                refresh_data = refresh_resp.json()
                print(f"   Old total: {refresh_data['old_total_memories']}")
                print(f"   New total: {refresh_data['new_total_memories']}")
                print(f"   Difference: {refresh_data['difference']}")
                print(f"   Message: {refresh_data['message']}")
            elif refresh_resp.status_code == 403:
                print(f"   ERROR: Invalid admin key. Set ADMIN_KEY env var or use: admin_key=refresh-stats-2025")
            else:
                print(f"   ERROR: Refresh returned {refresh_resp.status_code}")
                print(f"   Response: {refresh_resp.text}")
        except Exception as e:
            print(f"   ERROR: {e}")
        
        # Step 4: Verify fix
        print("\n4. Verifying fix...")
        try:
            # Check health again
            health_resp = await client.get(f"{base_url}/health")
            if health_resp.status_code == 200:
                health_data = health_resp.json()
                print(f"   Health endpoint now reports: {health_data['total_memories']} memories")
            
            # Check stats endpoint
            stats_resp = await client.get(f"{base_url}/memories/stats")
            if stats_resp.status_code == 200:
                stats_data = stats_resp.json()
                print(f"   Stats endpoint reports: {stats_data['total_memories']} memories")
                print(f"   By provider:")
                for provider, count in stats_data['memories_by_provider'].items():
                    print(f"     - {provider}: {count}")
            
            # Try a query
            query_resp = await client.post(
                f"{base_url}/memories/query",
                json={"query": "", "limit": 10}
            )
            if query_resp.status_code == 200:
                query_data = query_resp.json()
                print(f"   Query endpoint found: {query_data['total_found']} memories")
                print(f"   Returned: {len(query_data['memories'])} memories")
                
        except Exception as e:
            print(f"   ERROR during verification: {e}")


async def main():
    """Run the fix."""
    print("Core Nexus Sync Issue Fix Script")
    print("=" * 50)
    print(f"Started at: {datetime.now().isoformat()}")
    
    # Get API URL from environment or use default
    api_url = os.getenv("API_BASE_URL", "http://localhost:8000")
    
    # For production Render deployment
    if os.getenv("RENDER_SERVICE_NAME"):
        api_url = "https://core-nexus-memory.onrender.com"
        print(f"Detected Render deployment, using: {api_url}")
    
    # Check if API URL is provided as argument
    if len(sys.argv) > 1:
        api_url = sys.argv[1]
        print(f"Using API URL from argument: {api_url}")
    
    try:
        await fix_via_api(api_url)
        print("\n" + "=" * 50)
        print("Fix complete! The health endpoint should now report the correct number of memories.")
        print("\nNext steps:")
        print("1. Monitor the health endpoint to ensure counts stay synchronized")
        print("2. The initial stats sync will run automatically on service restart")
        print("3. Use the refresh-stats endpoint if counts drift again")
        
    except Exception as e:
        print(f"\nERROR: Fix failed with: {e}")
        print("\nTroubleshooting:")
        print("1. Make sure the API is running and accessible")
        print("2. Check that ADMIN_KEY environment variable is set correctly")
        print("3. Verify the API URL is correct")
        print(f"4. Current API URL: {api_url}")


if __name__ == "__main__":
    asyncio.run(main())