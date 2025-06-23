# MCP Personal - Collection of Personal MCP Servers

A collection of [Model Context Protocol](https://modelcontextprotocol.io) (MCP) servers for various personal productivity tools and utilities.

## Available MCP Servers

### 1. File Search Server (`mcp_fd_server.py`)
Powerful file search capabilities using `fd` and `fzf`:
- **Fast file search** using `fd` (a modern, user-friendly alternative to `find`)
- **Fuzzy filtering** with `fzf` for intelligent file matching
- **Multiline content search** for filtering entire file contents
- **Regex and glob pattern** support
- **Standalone CLI** for testing and direct usage

### 2. Fuzzy Search Server (`mcp_fuzzy_search.py`)
Advanced content search using `ripgrep` and `fzf`:
- **Content search** using `ripgrep` to search all lines in files
- **Fuzzy filtering** of search results using `fzf --filter`
- **Simplified interface** - just provide fuzzy search terms, no regex required
- **Multiline record processing** for complex pattern matching
- **Non-interactive** operation perfect for MCP integration
- **File path fuzzy search** for finding files by name patterns
- **Standalone CLI** for testing and direct usage

### 3. SQLite Server (`mcp_sqlite_server.py`)
SQLite database operations with configurable read/write permissions:
- **Read-only by default** - Write operations disabled unless explicitly enabled
- **Agent-friendly** - Clear tool descriptions and examples for easy AI agent usage
- **In-memory database support** - Use `:memory:` for temporary databases
- **Comprehensive operations** - Query, execute, list tables, describe schema, create tables
- **Safety features** - Query validation, write operation restrictions, clear error messages
- **Standalone CLI** for testing and direct usage

## Prerequisites

### General Requirements
- Python 3.10 or higher
- [uv](https://github.com/astral-sh/uv) (recommended) or pip

### File Search Server Requirements
The file search server requires the following command-line tools:

#### macOS
```bash
brew install fd fzf
```

#### Ubuntu/Debian
```bash
sudo apt install fd-find fzf
# Note: On Debian/Ubuntu, fd is installed as 'fdfind'
```

#### Other Systems
- [fd installation guide](https://github.com/sharkdp/fd#installation)
- [fzf installation guide](https://github.com/junegunn/fzf#installation)

### Fuzzy Search Server Requirements
The fuzzy search server requires:

#### macOS
```bash
brew install ripgrep fzf
```

#### Ubuntu/Debian
```bash
sudo apt install ripgrep fzf
```

#### Other Systems
- [ripgrep installation guide](https://github.com/BurntSushi/ripgrep#installation)
- [fzf installation guide](https://github.com/junegunn/fzf#installation)

## Installation

### Clone the Repository

```bash
git clone https://github.com/yourusername/mcp-personal.git
cd mcp-personal
```

### Configure MCP Servers

#### Using Claude Code CLI

The easiest way to add MCP servers to Claude Code is using the CLI:

```bash
# Add published npm servers (recommended to use -s user for global access)
claude mcp add sequential-thinking -s user -- npx -y @modelcontextprotocol/server-sequential-thinking

# Add custom Python servers from this repository
# IMPORTANT: Use -s user for personal tools you want available across all projects
# Without -s flag, servers are only available in current directory and are temporary

# Easy method: Use $(pwd) when in the project directory
cd /path/to/mcp-personal
claude mcp add file-search -s user -- $(pwd)/mcp_fd_server.py
claude mcp add fuzzy-search -s user -- $(pwd)/mcp_fuzzy_search.py
claude mcp add sqlite -s user -- $(pwd)/mcp_sqlite_server.py

# Or use relative paths (also from project directory)
claude mcp add file-search -s user -- ./mcp_fd_server.py
claude mcp add fuzzy-search -s user -- ./mcp_fuzzy_search.py
claude mcp add sqlite -s user -- ./mcp_sqlite_server.py

# Using absolute paths (works from anywhere)
claude mcp add file-search -s user -- /path/to/mcp-personal/mcp_fd_server.py
claude mcp add fuzzy-search -s user -- /path/to/mcp-personal/mcp_fuzzy_search.py
claude mcp add sqlite -s user -- /path/to/mcp-personal/mcp_sqlite_server.py

# Add SQLite server with write permissions enabled
claude mcp add sqlite -s user -- /path/to/mcp-personal/mcp_sqlite_server.py --allow-writes

# Or using environment variable
claude mcp add sqlite -s user -e MCP_SQLITE_ALLOW_WRITES=true -- /path/to/mcp-personal/mcp_sqlite_server.py

# Add Python servers with Python interpreter explicitly
claude mcp add my-server -s user -- python /path/to/my_mcp_server.py

# Add servers with arguments
claude mcp add my-server -s user -- python /path/to/server.py arg1 arg2

# Add servers with environment variables
claude mcp add my-server -s user -e API_KEY=your_key -e DEBUG=true -- python /path/to/server.py

# Scope options:
# -s local (default): Temporary, only in current directory
# -s project: Shared with team via .mcp.json file
# -s user: Personal, available across all your projects (recommended)
```

**Note:** 
- The `--` separator is important before the command and its arguments
- Environment variables use `-e KEY=value` syntax
- Use `-s user` for personal servers available across all projects
- Both relative and absolute paths work

#### Manual Configuration (Claude Desktop)

For Claude Desktop, manually add servers to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "file-search": {
      "command": "/path/to/mcp-personal/mcp_fd_server.py"
    },
    "fuzzy-search": {
      "command": "/path/to/mcp-personal/mcp_fuzzy_search.py"
    },
    "sqlite": {
      "command": "/path/to/mcp-personal/mcp_sqlite_server.py",
      "args": ["--allow-writes"],
      "env": {
        "MCP_SQLITE_ALLOW_WRITES": "true"
      }
    }
  }
}
```

### Make Scripts Executable

```bash
# Make all Python scripts executable
chmod +x *.py
```

### For Development

```bash
# Install with development dependencies
uv sync --dev

# Or use make
make setup
```

## Testing and Development

### MCP Inspector

The **MCP Inspector** is an interactive developer tool for testing and debugging MCP servers. It provides a web-based interface that allows you to:

- **Visually test your MCP servers** with an interactive UI
- **Debug server implementations** by examining request/response flows
- **Test tools, resources, and prompts** with different arguments
- **Validate server behavior** before deployment

#### Quick Testing

Test any MCP server using the inspector:

```bash
# Test the file search server
npx @modelcontextprotocol/inspector ./mcp_fd_server.py

# Test the fuzzy search server  
npx @modelcontextprotocol/inspector ./mcp_fuzzy_search.py

# Test the SQLite server (read-only mode)
npx @modelcontextprotocol/inspector ./mcp_sqlite_server.py

# Test the SQLite server with write permissions
npx @modelcontextprotocol/inspector ./mcp_sqlite_server.py -- --allow-writes
```

This will:
1. Start the MCP Inspector proxy server (default port 6277)
2. Launch a web interface (default port 6274) 
3. Connect to your MCP server via stdio transport
4. Open your browser to the inspector interface

#### Using the Inspector

Once the inspector is running:

1. **Navigate to the web interface** (usually http://localhost:6274)
2. **Explore the tabs**:
   - **Tools**: Test `search_files`, `filter_files`, `fuzzy_search_files`, `fuzzy_search_content`
   - **Resources**: View any exposed resources (if implemented)
   - **Prompts**: Test any exposed prompts (if implemented)
3. **Test different scenarios**:
   - Try various search patterns and filters
   - Test multiline functionality
   - Experiment with different file paths and flags
   - Validate error handling with invalid inputs

#### Advanced Configuration

You can also use configuration files for complex setups:

```bash
# Using a config file
npx @modelcontextprotocol/inspector --config config.json

# Passing environment variables
npx @modelcontextprotocol/inspector -e "DEBUG=1" ./mcp_fuzzy_search.py

# Custom ports
npx @modelcontextprotocol/inspector --mcpp-port 3001 --mcpi-port 3002 ./mcp_fd_server.py
```

The MCP Inspector is particularly valuable for:
- **Rapid prototyping** - quickly test new functionality
- **Debugging** - identify issues before integration with Claude
- **Documentation** - understand exactly what your server exposes
- **Validation** - ensure proper error handling and edge cases

## Usage

### File Search Server

#### As an MCP Server

Once configured in Claude Desktop, you can use natural language to search for files:

- "Find all Python files in the src directory"
- "Search for files containing 'config' in their name"
- "Find test files modified in the last week"

#### CLI Usage

The file search server also works as a standalone CLI tool:

```bash
# Search for files matching a pattern
./mcp_fd_server.py search "\.py$" /path/to/search

# Search with additional fd flags
./mcp_fd_server.py search "\.js$" . --flags "--hidden --no-ignore"

# Fuzzy filter results
./mcp_fd_server.py filter "main" "\.py$" /path/to/search

# Get the best match only
./mcp_fd_server.py filter "app" "" . --first

# Multiline content search - search entire file contents
./mcp_fd_server.py filter "class.*function" "" src --multiline
```

### Fuzzy Search Server

#### As an MCP Server

Once configured in Claude Desktop, you can use natural language for advanced searching:

- "Search for TODO comments that mention 'implement'"
- "Find all files with 'test' in the name using fuzzy search"
- "Look for error handling code in Python files"
- "Search for configuration files containing database settings"
- "Find method definitions named 'update_ondemand_max_spend'"
- "Search for async functions with error handling"

#### CLI Usage

The fuzzy search server also works as a standalone CLI tool:

```bash
# Fuzzy search for file paths
./mcp_fuzzy_search.py search-files "main" /path/to/search
./mcp_fuzzy_search.py search-files "test" . --hidden --limit 10

# Search all content and filter with fzf (like 'rg . | fzf')
./mcp_fuzzy_search.py search-content "TODO implement" .
./mcp_fuzzy_search.py search-content "error handle" src --rg-flags "-i"

# Multiline content search - treat each file as a single record
./mcp_fuzzy_search.py search-files "class.*constructor" src --multiline
./mcp_fuzzy_search.py search-content "async.*await" . --multiline
```

### SQLite Server

#### As an MCP Server

Once configured in Claude Desktop, you can use natural language for database operations:

- "List all tables in the database"
- "Show me the schema for the users table"
- "Query the last 10 orders from the orders table"
- "Count active users in the database"
- "Update user status to inactive for users who haven't logged in for a year" (requires write permissions)
- "Create a new table for storing session data" (requires write permissions)

#### CLI Usage

The SQLite server also works as a standalone CLI tool:

```bash
# Query database (read-only operations)
./mcp_sqlite_server.py query "SELECT * FROM users" database.db
./mcp_sqlite_server.py query "SELECT COUNT(*) as total FROM orders WHERE status = 'active'" sales.db

# List all tables
./mcp_sqlite_server.py list-tables database.db

# Describe table schema
./mcp_sqlite_server.py describe-table users database.db

# Execute write operations (requires --allow-writes flag)
./mcp_sqlite_server.py execute "INSERT INTO users (name, email) VALUES ('John', 'john@example.com')" database.db --allow-writes
./mcp_sqlite_server.py execute "UPDATE users SET active = 0 WHERE last_login < date('now', '-1 year')" database.db --allow-writes

# Use in-memory database for testing
./mcp_sqlite_server.py query "SELECT sqlite_version()" :memory:
```

## Multiline Search Mode

Both MCP servers support **multiline search mode** for advanced pattern matching across entire file contents, making it possible to find complex patterns that span multiple lines.

### What is Multiline Mode?

In multiline mode:
- **File Search Server**: Reads each file's complete content and treats it as a single multiline record for fuzzy filtering
- **Fuzzy Search Server**: Processes files as complete units rather than line-by-line, enabling pattern matching across line boundaries

### When to Use Multiline Mode

Multiline mode is perfect for:
- **Finding class definitions** with their methods: `"class UserService.*authenticate"`
- **Locating function implementations** with specific patterns: `"async function.*await.*fetch"`
- **Searching for configuration blocks**: `"database.*host.*port"`
- **Finding code structures** that span multiple lines: `"try.*catch.*finally"`
- **Identifying file contents** by structure rather than individual lines

### Multiline Examples

#### File Search Server Multiline
```bash
# Find JavaScript files containing complete class definitions
./mcp_fd_server.py filter "class.*constructor.*method" "" src --multiline

# Find Python files with specific class and method patterns  
./mcp_fd_server.py filter "class.*def.*return" "" . --multiline

# Find configuration files with database connection blocks
./mcp_fd_server.py filter "database.*host.*password" "" config --multiline
```

#### Fuzzy Search Server Multiline
```bash
# Find files containing async function definitions
./mcp_fuzzy_search.py search-files "async.*function.*await" src --multiline

# Search for files with specific multi-line patterns
./mcp_fuzzy_search.py search-content "try.*catch.*finally" . --multiline

# Find files with class definitions containing specific methods
./mcp_fuzzy_search.py search-content "class.*constructor.*render" src --multiline
```

### Performance Considerations

- **File size**: Multiline mode reads entire files into memory; best for typical source code files
- **Result size**: Multiline results include complete file contents, which may be truncated for display
- **Pattern complexity**: Simple patterns work well; very complex regex may be slower

### Tips for Multiline Queries

1. **Use specific terms**: `"class MyClass.*def method"` is better than just `"class.*def"`
2. **Combine structure and content**: `"import React.*export default"` finds React components
3. **Mind the output**: Results show the entire matching file content
4. **Test incrementally**: Start with simple patterns and refine

## fzf Search Syntax Guide

Both MCP servers use **fzf's extended search syntax** for powerful fuzzy filtering. Understanding this syntax will help you construct precise queries.

### Basic Syntax

| Pattern | Description | Example |
|---------|-------------|---------|
| `term` | Fuzzy match (default) | `config` matches "configuration" |
| `term1 term2` | AND logic (all terms must match) | `main config` requires both terms |
| `term1 \| term2` | OR logic (any term can match) | `py$ \| js$ \| go$` matches files ending in any |

### Exact Matching

| Pattern | Description | Example |
|---------|-------------|---------|
| `'term` | Partial exact match | `'main` exactly matches "main" substring |
| `'term'` | Exact boundary match | `'main.py'` matches exactly at word boundaries |

### Position Anchors

| Pattern | Description | Example |
|---------|-------------|---------|
| `^term` | Prefix match (starts with) | `^src` matches "src/file.py" |
| `term$` | Suffix match (ends with) | `.json$` matches "config.json" |
| `^term$` | Exact match (entire string) | `^README$` matches only "README" |

### Negation (Exclusion)

| Pattern | Description | Example |
|---------|-------------|---------|
| `!term` | Exclude fuzzy matches | `config !test` excludes test files |
| `!'term` | Exclude exact matches | `!'backup'` excludes files with exact "backup" |
| `!^term` | Exclude prefix matches | `!^.` excludes hidden files |
| `!term$` | Exclude suffix matches | `!.tmp$` excludes temporary files |

### Advanced Examples

```bash
# Find Python configuration files, excluding tests
config .py$ !test

# Find main files in src directory with multiple extensions  
^src/ main py$ | js$ | go$

# Find exact package manager files
'package.json' | 'yarn.lock' | 'Pipfile'

# Find TODO comments in code files, excluding documentation
TODO .py$ | .js$ | .go$ !README !docs/

# Find function definitions, excluding test files
'def ' .py$ !test !spec

# Find configuration files with specific extensions, excluding backups
config .json$ | .yaml$ | .toml$ !.bak$ !.old$
```

### Content Search Specific Patterns

When using `fuzzy_search_content`, queries work on the format `file:line:content`:

```bash
# Find implementation TODOs in specific file types
TODO implement .py: | .js:

# Find error handling in specific files
error 'main.py:' | 'app.js:'

# Find async functions with error handling
'async def' error .py$

# Find class definitions excluding test files
'class ' .py: !test !spec

# Find imports from specific modules
'import' react | lodash | numpy
```

## ripgrep (rg) Flags Reference

The `fuzzy_search_content` tool accepts `rg_flags` for enhanced searching. Here are the most useful flags:

### Case Sensitivity
| Flag | Description | Example |
|------|-------------|---------|
| `-i, --ignore-case` | Case insensitive search | `rg -i "todo"` matches TODO, Todo, todo |
| `-S, --smart-case` | Case insensitive if lowercase, sensitive if mixed | `rg -S "Todo"` is case sensitive |
| `-s, --case-sensitive` | Force case sensitive (default) | `rg -s "TODO"` matches only TODO |

### File Type Filtering
| Flag | Description | Example |
|------|-------------|---------| 
| `-t TYPE` | Only search specific file types | `-t py` searches Python files only |
| `-T TYPE` | Exclude specific file types | `-T test` excludes test files |
| `--type-list` | Show all supported file types | `rg --type-list` |

### Context Lines
| Flag | Description | Example |
|------|-------------|---------| 
| `-A NUM` | Show NUM lines after match | `-A 3` shows 3 lines after |
| `-B NUM` | Show NUM lines before match | `-B 2` shows 2 lines before |
| `-C NUM` | Show NUM lines before and after | `-C 3` shows 3 lines both sides |

### File Handling
| Flag | Description | Example |
|------|-------------|---------| 
| `--hidden` | Search hidden files/directories | `--hidden` includes .hidden files |
| `--no-ignore` | Ignore .gitignore rules | `--no-ignore` searches ignored files |
| `-u` | Reduce filtering (1-3 times) | `-uu` = `--no-ignore --hidden` |

### Pattern Matching
| Flag | Description | Example |
|------|-------------|---------| 
| `-F` | Literal string search (no regex) | `-F` searches for exact text |
| `-w` | Match whole words only | `-w` won't match partial words |
| `-v` | Invert match (show non-matches) | `-v` shows lines without matches |
| `-x` | Match entire lines only | `-x` matches exact line |

### Advanced Features
| Flag | Description | Example |
|------|-------------|---------| 
| `-U` | Enable multiline matching | `-U` (note: use multiline parameter instead) |
| `-P` | Use PCRE2 regex engine | `-P` for advanced regex features |
| `-o` | Show only matching parts | `-o` shows just matching text |

### Output Control
| Flag | Description | Example |
|------|-------------|---------| 
| `-c` | Count matches per file | `-c` shows count only |
| `-l` | Show only filenames with matches | `-l` lists files with matches |
| `--column` | Show column numbers | `--column` includes column info |

### Practical Combinations

```bash
# Case-insensitive search with context in Python files
rg_flags: "-i -C 3 -t py"

# Search all files including hidden and ignored, with context
rg_flags: "-uu -C 2"

# Find exact function signatures in code files
rg_flags: "-F -w -t py -t js -t go"

# Search for TODOs with file types, case insensitive, show context
rg_flags: "-i -C 1 -t py -t js --no-ignore"

# Multi-line class definitions with context
rg_flags: "-U -C 3 -t py"

# Literal string search in all text files
rg_flags: "-F --no-ignore -t txt -t md -t rst"
```

## MCP Tools Documentation

### File Search Server Tools

#### `search_files`
Find files using fd with regex or glob patterns.

**Parameters:**
- `pattern` (required): Regex or glob pattern to match
- `path` (optional): Directory to search in (defaults to current directory)
- `flags` (optional): Additional flags to pass to fd

**Example:**
```python
{
  "pattern": r"\.py$",
  "path": "/home/user/projects",
  "flags": "--hidden --no-ignore"
}
```

#### `filter_files`
Search for files and filter results using fzf's fuzzy matching.

**Parameters:**
- `filter` (required): String to fuzzy match against file paths
- `pattern` (optional): Initial pattern for fd
- `path` (optional): Directory to search in
- `first` (optional): Return only the best match
- `fd_flags` (optional): Extra flags for fd
- `fzf_flags` (optional): Extra flags for fzf
- `multiline` (optional): Enable multiline content search (default: false)

**Example:**
```python
{
  "filter": "test",
  "pattern": r"\.py$",
  "path": "./src",
  "first": true
}
```

**Multiline Example:**
```python
{
  "filter": "class.*function.*return",
  "pattern": "",
  "path": "./src",
  "multiline": true
}
```

### Fuzzy Search Server Tools

#### `fuzzy_search_files`
Search for file paths using fuzzy matching.

**Parameters:**
- `filter` (required): Fuzzy search string
- `path` (optional): Directory to search in (defaults to current directory)
- `hidden` (optional): Include hidden files (default: false)
- `limit` (optional): Maximum results to return (default: 20)
- `multiline` (optional): Enable multiline file content search (default: false)

**Example:**
```python
{
  "filter": "main",
  "path": "/home/user/projects",
  "hidden": true,
  "limit": 10
}
```

**Multiline Example:**
```python
{
  "filter": "import.*export",
  "path": "./src",
  "multiline": true,
  "limit": 5
}
```

#### `fuzzy_search_content`
Search all file contents using fuzzy filtering.

**Parameters:**
- `fuzzy_filter` (required): Fuzzy search query for filtering results
- `path` (optional): Directory/file to search in (defaults to current directory)
- `hidden` (optional): Search hidden files (default: false)
- `limit` (optional): Maximum results to return (default: 20)
- `rg_flags` (optional): Extra flags for ripgrep (see ripgrep flags reference)
- `multiline` (optional): Enable multiline record processing (default: false)

**Example:**
```python
{
  "fuzzy_filter": "TODO implement",
  "path": "./src",
  "rg_flags": "-i",
  "limit": 15
}
```

**Multiline Example:**
```python
{
  "fuzzy_filter": "async.*await.*catch",
  "path": "./src",
  "multiline": true,
  "limit": 10
}
```

### SQLite Server Tools

#### `query`
Execute SELECT queries on the database.

**Parameters:**
- `sql` (required): SELECT query to execute
- `db_path` (optional): Path to SQLite database (defaults to configured db_path or ':memory:')

**Example:**
```python
{
  "sql": "SELECT * FROM users WHERE active = 1 ORDER BY created_at DESC LIMIT 10",
  "db_path": "myapp.db"
}
```

#### `execute`
Execute INSERT, UPDATE, or DELETE queries (requires write permissions).

**Parameters:**
- `sql` (required): INSERT, UPDATE, or DELETE query to execute
- `db_path` (optional): Path to SQLite database

**Example:**
```python
{
  "sql": "UPDATE users SET last_login = datetime('now') WHERE id = 123",
  "db_path": "myapp.db"
}
```

#### `list_tables`
List all tables in the database.

**Parameters:**
- `db_path` (optional): Path to SQLite database

**Example:**
```python
{
  "db_path": "myapp.db"
}
```

#### `describe_table`
Get detailed schema information for a specific table, including columns, types, constraints, and indexes.

**Parameters:**
- `table_name` (required): Name of the table to describe
- `db_path` (optional): Path to SQLite database

**Example:**
```python
{
  "table_name": "users",
  "db_path": "myapp.db"
}
```

#### `create_table`
Create a new table with specified columns (requires write permissions).

**Parameters:**
- `table_name` (required): Name of the table to create
- `columns` (required): List of column definitions
- `db_path` (optional): Path to SQLite database

**Column Definition:**
- `name` (required): Column name
- `type` (required): SQLite data type (TEXT, INTEGER, REAL, BLOB, etc.)
- `constraints` (optional): Column constraints (PRIMARY KEY, NOT NULL, UNIQUE, etc.)

**Example:**
```python
{
  "table_name": "sessions",
  "columns": [
    {
      "name": "id",
      "type": "TEXT",
      "constraints": "PRIMARY KEY"
    },
    {
      "name": "user_id",
      "type": "INTEGER",
      "constraints": "NOT NULL"
    },
    {
      "name": "created_at",
      "type": "TIMESTAMP",
      "constraints": "DEFAULT CURRENT_TIMESTAMP"
    },
    {
      "name": "expires_at",
      "type": "TIMESTAMP",
      "constraints": "NOT NULL"
    }
  ],
  "db_path": "myapp.db"
}
```

## Development

### Project Structure
```
mcp-personal/
├── mcp_fd_server.py      # File search MCP server
├── mcp_fuzzy_search.py   # Fuzzy content search MCP server
├── mcp_sqlite_server.py  # SQLite database MCP server
├── tests/                # Test suite
│   ├── test_simple.py    # Direct function tests
│   ├── test_fd_server.py # File search MCP integration tests
│   ├── test_fuzzy_search.py # Fuzzy search tests
│   ├── test_sqlite_server.py # SQLite server tests
│   └── test_cli.py       # CLI interface tests
├── pyproject.toml        # Project configuration
├── Makefile              # Development commands
├── CLAUDE.md             # Claude-specific instructions
└── README.md             # This file
```

### Adding New MCP Servers

To add a new MCP server to this collection:

1. Create a new Python file (e.g., `mcp_new_server.py`)
2. Implement using FastMCP framework
3. Add tests in the `tests/` directory
4. Update this README with documentation
5. Add configuration example for Claude Desktop

### Running Tests

```bash
# Run all tests
make test

# Run specific test categories
make test-simple  # Direct function tests
make test-cli     # CLI interface tests
make test-full    # Full MCP integration tests

# Run with coverage
make test-cov
```

### Development Commands

```bash
make help         # Show all available commands
make setup        # Install development dependencies
make test         # Run tests
make lint         # Run linting
make format       # Format code
make type-check   # Run type checking
make clean        # Clean generated files
```

### Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Make your changes
4. Run tests (`make test`)
5. Run linting (`make check`)
6. Commit your changes
7. Push to the branch (`git push origin feature/amazing-feature`)
8. Open a Pull Request

## Architecture

All MCP servers in this collection are built using:
- **FastMCP**: High-level MCP server framework from the official Python SDK
- **uv**: Fast Python package manager
- **Self-contained scripts**: Each server uses `#!/usr/bin/env -S uv run --script` for easy deployment

### File Search Server
Additionally uses:
- **fd**: Modern file finder written in Rust
- **fzf**: Command-line fuzzy finder

### Fuzzy Search Server
Additionally uses:
- **ripgrep**: Extremely fast search tool that respects gitignore
- **fzf**: Command-line fuzzy finder (used in filter mode)

## Security Considerations

### General
- All servers run with the permissions of the user executing them
- Consider the security implications of each server's capabilities
- Review server code before installation

### File Search Server
- Has filesystem access based on user permissions
- Be cautious when searching in sensitive directories
- The `--no-ignore` flag will include files normally hidden by `.gitignore`

### Fuzzy Search Server
- Has filesystem read access based on user permissions
- Can search file contents, including source code and configuration files
- Respects `.gitignore` by default (use `--hidden` to include ignored files)
- Be mindful when searching in repositories with sensitive data

### SQLite Server
- **Read-only by default** - Prevents accidental data modification
- Write operations require explicit `--allow-writes` flag or environment variable
- Has full database access based on file permissions
- Can execute arbitrary SQL queries when write mode is enabled
- Be extremely cautious with write permissions on production databases
- Consider using separate read-only database users when possible

## Troubleshooting

### "Cannot find the `fd` binary"
- Ensure fd is installed and in your PATH
- On Debian/Ubuntu, fd might be installed as `fdfind`

### "Cannot find the `fzf` binary"
- Install fzf using your package manager
- Ensure it's available in your PATH

### Tests failing
- Check that required binaries are installed for each server
- Run `make check-deps` to verify binaries are available
- Some tests require a Unix-like environment

## License

This project is open source and available under the [MIT License](LICENSE).

## Acknowledgments

- [Model Context Protocol](https://modelcontextprotocol.io) - The protocol enabling AI-tool interactions
- [FastMCP](https://github.com/jlowin/fastmcp) - The Python framework for building MCP servers
- [uv](https://github.com/astral-sh/uv) - An extremely fast Python package installer and resolver

### File Search Server
- [fd](https://github.com/sharkdp/fd) - A simple, fast and user-friendly alternative to find
- [fzf](https://github.com/junegunn/fzf) - A command-line fuzzy finder

### Fuzzy Search Server
- [ripgrep](https://github.com/BurntSushi/ripgrep) - Recursively search directories for text patterns
- [fzf](https://github.com/junegunn/fzf) - A command-line fuzzy finder

### SQLite Server
- [SQLite](https://www.sqlite.org/) - Self-contained, serverless, zero-configuration SQL database engine