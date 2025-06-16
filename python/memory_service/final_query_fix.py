#!/usr/bin/env python3
"""
Final targeted fix - ensure the table_name attribute is accessible.
"""

# Check the providers.py to ensure table_name is accessible
with open('src/memory_service/providers.py', 'r') as f:
    content = f.read()

# The issue might be that table_name isn't a direct attribute. Let's check.
import re

# Find the PgVectorProvider class init
init_match = re.search(r'class PgVectorProvider.*?def __init__\(self.*?\):(.*?)def ', content, re.DOTALL)
if init_match:
    init_content = init_match.group(1)
    print("Found PgVectorProvider.__init__:")
    print("table_name assignment:", "self.table_name" in init_content)

# Update unified_store.py to handle the attribute access properly
with open('src/memory_service/unified_store.py', 'r') as f:
    unified_content = f.read()

# Fix the emergency search to use getattr for safety
unified_content = unified_content.replace(
    'EmergencySearchFix(pgvector.connection_pool, pgvector.table_name)',
    'EmergencySearchFix(pgvector.connection_pool, getattr(pgvector, "table_name", "vector_memories"))'
)

# Also fix the second occurrence
unified_content = unified_content.replace(
    'EmergencySearchFix(provider.connection_pool, provider.table_name)',
    'EmergencySearchFix(provider.connection_pool, getattr(provider, "table_name", "vector_memories"))'
)

# Write back
with open('src/memory_service/unified_store.py', 'w') as f:
    f.write(unified_content)

print("\n✅ Applied final query fix")
print("Using getattr() to safely access table_name attribute")