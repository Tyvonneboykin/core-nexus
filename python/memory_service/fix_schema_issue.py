#!/usr/bin/env python3
"""
Fix potential schema issues with the pgvector table.
The issue might be that we're querying the wrong schema or the table is in a different schema.
"""

# Read current search_fix.py
with open('src/memory_service/search_fix.py', 'r') as f:
    content = f.read()

# Update to check schema and use fully qualified table names
updated_content = content.replace(
    """                # First, let's check what tables exist
                table_check = await conn.fetchval(f\"\"\"
                    SELECT COUNT(*) 
                    FROM information_schema.tables 
                    WHERE table_name = '{self.table_name}'
                \"\"\")""",
    """                # First, let's check what tables exist in all schemas
                table_info = await conn.fetch(f\"\"\"
                    SELECT table_schema, table_name 
                    FROM information_schema.tables 
                    WHERE table_name = '{self.table_name}' 
                       OR table_name LIKE '%memor%'
                       OR table_name LIKE '%vector%'
                    ORDER BY table_schema, table_name
                \"\"\")
                
                logger.info(f"Found tables: {[(t['table_schema'], t['table_name']) for t in table_info]}")
                
                # Find the correct schema
                schema_name = 'public'  # default
                table_found = False
                
                for table in table_info:
                    if table['table_name'] == self.table_name and table['table_schema'] != 'information_schema':
                        schema_name = table['table_schema']
                        table_found = True
                        break
                
                if not table_found and table_info:
                    # Use the first memory-related table found
                    for table in table_info:
                        if 'memor' in table['table_name'] and table['table_schema'] not in ('information_schema', 'pg_catalog'):
                            schema_name = table['table_schema']
                            self.table_name = table['table_name']
                            logger.info(f"Using table: {schema_name}.{self.table_name}")
                            break
                
                # Use fully qualified table name
                full_table_name = f"{schema_name}.{self.table_name}"
                
                table_check = 1""")

# Also update all other references to use full_table_name
updated_content = updated_content.replace(
    'FROM {self.table_name}',
    'FROM {full_table_name}'
)

updated_content = updated_content.replace(
    'f"SELECT COUNT(*) FROM {self.table_name}"',
    'f"SELECT COUNT(*) FROM {full_table_name}"'
)

# Fix the variable scope issue
updated_content = updated_content.replace(
    """                # Get total count first
                total_count = await conn.fetchval(f"SELECT COUNT(*) FROM {full_table_name}")
                logger.info(f"Total memories in {full_table_name}: {total_count}")""",
    """                # Get total count first
                full_table_name = f"{schema_name}.{self.table_name}"
                total_count = await conn.fetchval(f"SELECT COUNT(*) FROM {full_table_name}")
                logger.info(f"Total memories in {full_table_name}: {total_count}")""")

# Write back
with open('src/memory_service/search_fix.py', 'w') as f:
    f.write(updated_content)

print("✅ Updated search_fix.py to handle schema issues")
print("\nChanges made:")
print("1. Check all schemas for memory-related tables")
print("2. Use fully qualified table names (schema.table)")
print("3. Better table discovery logic")
print("4. Added detailed logging for debugging")