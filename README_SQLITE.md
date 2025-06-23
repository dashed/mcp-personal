# SQLite MCP Server

A Model Context Protocol (MCP) server for SQLite database operations with configurable read/write permissions.

## Features

- **Read-only by default** - Write operations are disabled unless explicitly enabled
- **Agent-friendly** - Clear tool descriptions and examples for easy AI agent usage
- **In-memory database support** - Use `:memory:` for temporary databases
- **Comprehensive operations** - Query, execute, list tables, describe schema, create tables

## Tools

### `query`
Execute SELECT queries on the database.

```sql
query("SELECT * FROM users")
query("SELECT COUNT(*) as total FROM orders WHERE status = 'active'")
```

### `execute`
Execute INSERT, UPDATE, or DELETE queries (requires write permissions).

```sql
execute("INSERT INTO users (name, email) VALUES ('John', 'john@example.com')")
execute("UPDATE users SET active = 0 WHERE last_login < date('now', '-1 year')")
execute("DELETE FROM sessions WHERE expired = 1")
```

### `list_tables`
List all tables in the database.

### `describe_table`
Get detailed schema information for a specific table, including columns, types, constraints, and indexes.

### `create_table`
Create a new table with specified columns (requires write permissions).

```python
columns = [
    {"name": "id", "type": "INTEGER", "constraints": "PRIMARY KEY AUTOINCREMENT"},
    {"name": "email", "type": "TEXT", "constraints": "UNIQUE NOT NULL"},
    {"name": "created_at", "type": "TIMESTAMP", "constraints": "DEFAULT CURRENT_TIMESTAMP"}
]
create_table("users", columns)
```

## Usage

### As MCP Server

```bash
# Read-only mode (default)
./mcp_sqlite_server.py

# Enable write operations
./mcp_sqlite_server.py --allow-writes

# Set default database
./mcp_sqlite_server.py --db-path /path/to/database.db

# Enable writes via environment variable
MCP_SQLITE_ALLOW_WRITES=true ./mcp_sqlite_server.py
```

### CLI Testing

```bash
# Query database
./mcp_sqlite_server.py query "SELECT * FROM users" database.db

# List tables
./mcp_sqlite_server.py list-tables database.db

# Describe table schema
./mcp_sqlite_server.py describe-table users database.db
```

### MCP Client Configuration

Add to your MCP client configuration:

```json
{
  "sqlite": {
    "command": "python",
    "args": ["/path/to/mcp_sqlite_server.py", "--allow-writes"],
    "env": {
      "MCP_SQLITE_ALLOW_WRITES": "true"
    }
  }
}
```

## Safety Features

1. **Read-only by default** - Prevents accidental data modification
2. **Query validation** - Only SELECT queries allowed in query tool
3. **Write operation validation** - Only INSERT, UPDATE, DELETE allowed in execute tool
4. **Clear error messages** - Helpful guidance when operations are restricted

## Examples for AI Agents

When using this server, you can:

1. **Explore a database**:
   ```
   1. Use list_tables() to see all tables
   2. Use describe_table("table_name") to understand schema
   3. Use query("SELECT * FROM table_name LIMIT 5") to see sample data
   ```

2. **Analyze data**:
   ```sql
   query("SELECT COUNT(*) FROM users WHERE active = 1")
   query("SELECT DATE(created_at) as date, COUNT(*) as signups FROM users GROUP BY date")
   ```

3. **Modify data** (with write permissions):
   ```sql
   execute("UPDATE products SET price = price * 1.1 WHERE category = 'electronics'")
   execute("DELETE FROM logs WHERE created_at < date('now', '-30 days')")
   ```

## Testing

Run the test suite:

```bash
uv run pytest tests/test_sqlite_server.py -v
```

The tests use in-memory SQLite databases for fast, isolated testing.