# MCP Personal - Collection of Personal MCP Servers

A collection of [Model Context Protocol](https://modelcontextprotocol.io) (MCP) servers for various personal productivity tools and utilities.

## Available MCP Servers

### 1. File Search Server (`mcp_fd_server.py`)
Fuzzy file NAME search capabilities using `fd` and `fzf`:
- **Fast file name search** using `fd` (searches file names/paths, NOT contents)
- **Fuzzy filtering of file names** with `fzf` for intelligent name matching
- **Pattern matching** with regex and glob support for file names
- **Multiline mode** (advanced): can also search file contents when enabled
- **Standalone CLI** for testing and direct usage
- **Key point**: Primary purpose is finding files by NAME, not searching contents

### 2. Fuzzy Search Server (`mcp_fuzzy_search.py`)
Advanced search with both file name and content capabilities using `ripgrep` and `fzf`:
- **File name fuzzy search** - find files by partial/fuzzy names
- **Content search** using `ripgrep` to search text within files
- **Fuzzy filtering** of results using `fzf --filter`
- **Two distinct modes**: 
  - `fuzzy_search_files`: Search file NAMES/paths
  - `fuzzy_search_content`: Search file CONTENTS with path+content matching by default
- **PDF and document search** (optional) - search through PDFs, Office docs, and archives using `ripgrep-all`
- **PDF page extraction** (optional) - extract specific pages from PDFs using PyMuPDF with page label support
- **PDF information tools** (optional) - get page labels, page count, and table of contents from PDF files:
  - `get_pdf_page_labels`: Get all page labels from a PDF file
  - `get_pdf_page_count`: Get the total number of pages in a PDF file
  - `get_pdf_outline`: Extract table of contents/bookmarks from a PDF file
- **Simplified interface** - just provide fuzzy search terms (NO regex support)
- **Multiline record processing** for complex pattern matching
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

To install uv:
```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh

# Or using pip (if you already have Python)
pip install uv
```

### Note on Optional Features
The PDF search and extraction tools in the Fuzzy Search Server are **optional**. The server will work without these binaries installed - only the PDF-specific tools will be unavailable. This allows you to use the core fuzzy search functionality without requiring all dependencies.

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

# For PDF search capabilities (optional)
brew install ripgrep-all pandoc
pip install PyMuPDF  # Or: uv pip install PyMuPDF
```

#### Ubuntu/Debian
```bash
sudo apt install ripgrep fzf

# For PDF search capabilities (optional)
# Install ripgrep-all
cargo install ripgrep-all  # Requires Rust/cargo

# Install PyMuPDF
pip install PyMuPDF  # Or: uv pip install PyMuPDF

# Install pandoc
sudo apt install pandoc
```

#### Other Systems
- [ripgrep installation guide](https://github.com/BurntSushi/ripgrep#installation)
- [fzf installation guide](https://github.com/junegunn/fzf#installation)
- [ripgrep-all installation](https://github.com/phiresky/ripgrep-all#installation) (optional, for PDF search)
- [pandoc installation](https://pandoc.org/installing.html) (optional, for PDF extraction)

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
   - **Tools**: Test `search_files`, `filter_files`, `fuzzy_search_files`, `fuzzy_search_content`, `fuzzy_search_documents`, `extract_pdf_pages`
   - **Resources**: View any exposed resources (if implemented)
   - **Prompts**: Test any exposed prompts (if implemented)
3. **Test different scenarios**:
   - Try various search patterns and filters
   - Test multiline functionality
   - Experiment with different file paths and flags
   - Test PDF search with `fuzzy_search_documents` (if binaries installed)
   - Test PDF page extraction with `extract_pdf_pages` (if binaries installed)
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

Once configured in Claude Desktop, you can use natural language to search for files by NAME:

- "Find all Python files in the src directory" (searches file names ending in .py)
- "Search for files with 'config' in their name" (fuzzy matches file names)
- "Find test files by name" (searches for files with 'test' in the name)
- "Use fuzzy search to find 'mainpy'" (finds main.py, main_py.txt, etc.)

#### CLI Usage

The file search server also works as a standalone CLI tool:

```bash
# Search for files by name pattern
./mcp_fd_server.py search "\.py$" /path/to/search  # Find Python files by name

# Search with additional fd flags
./mcp_fd_server.py search "\.js$" . --flags "--hidden --no-ignore"

# Fuzzy filter file names/paths
./mcp_fd_server.py filter "main" "\.py$" /path/to/search  # Fuzzy search for 'main' in Python file names

# Get the best fuzzy match by name
./mcp_fd_server.py filter "app" "" . --first  # Find file with name most similar to 'app'

# Multiline mode - search file CONTENTS (not just names)
./mcp_fd_server.py filter "class function" "" src --multiline  # Find files containing both terms
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
- "Search for 'update' in test.py files only" (works because default mode matches paths too!)
- "Search for 'async' in content only, ignore file paths" (use content_only mode)
- "Search for 'vector' in PDF documents" (requires ripgrep-all)
- "Find all references to 'machine learning' in PDFs and Word documents"
- "Extract pages 5-10 from the user manual PDF"
- "Get the table of contents from the research paper PDF"
- "Show me the outline of chapters in the user manual"

#### CLI Usage

The fuzzy search server also works as a standalone CLI tool:

```bash
# Fuzzy search for file NAMES/PATHS
./mcp_fuzzy_search.py search-files "main" /path/to/search  # Find files with 'main' in the name
./mcp_fuzzy_search.py search-files "test" . --hidden --limit 10  # Find test files by name
./mcp_fuzzy_search.py search-files "config" / --confirm-root  # Search from root (requires explicit confirmation)

# Search file CONTENTS and filter with fzf (NO regex support)
# Default: Matches on BOTH file paths AND content
./mcp_fuzzy_search.py search-content "TODO implement" .  # Find lines containing both terms
./mcp_fuzzy_search.py search-content "test.py: update" .  # Find 'update' in test.py files
./mcp_fuzzy_search.py search-content "error handle" src --rg-flags "-i"  # Case insensitive
./mcp_fuzzy_search.py search-content "config" / --confirm-root  # Search from root (requires explicit confirmation)

# Content-only mode: Match ONLY on content, ignore file paths
./mcp_fuzzy_search.py search-content "TODO implement" . --content-only  # Pure content search
./mcp_fuzzy_search.py search-content "async await" src --content-only  # Won't match file paths

# Multiline mode - changes behavior:
# search-files --multiline: Searches file CONTENTS instead of names
./mcp_fuzzy_search.py search-files "class constructor" src --multiline  # Find files CONTAINING these terms

# search-content --multiline: Treats whole files as searchable units
./mcp_fuzzy_search.py search-content "async await" . --multiline  # Find files with both terms anywhere
./mcp_fuzzy_search.py search-content "try catch" . --multiline --content-only  # Content-only + multiline

# PDF and document search (requires optional binaries)
./mcp_fuzzy_search.py search-documents "machine learning" .  # Search PDFs and docs
./mcp_fuzzy_search.py search-documents "invoice total" invoices/ --file-types "pdf"  # PDFs only
./mcp_fuzzy_search.py search-documents "contract" . --file-types "pdf,docx" --limit 5
./mcp_fuzzy_search.py search-documents "report" / --confirm-root  # Search from root (requires explicit confirmation)

# Extract specific pages from PDFs (using PyMuPDF)
./mcp_fuzzy_search.py extract-pdf manual.pdf "1,3,5-7"  # Extract pages 1, 3, 5, 6, 7
./mcp_fuzzy_search.py extract-pdf report.pdf "v-vii,1,ToC"  # Use page labels
./mcp_fuzzy_search.py extract-pdf report.pdf "10-20" --format html  # Extract as HTML
./mcp_fuzzy_search.py extract-pdf thesis.pdf "100-105" --preserve-layout  # Keep layout
./mcp_fuzzy_search.py extract-pdf book.pdf "1-50" --fuzzy-hint "neural network"  # Filter by content
./mcp_fuzzy_search.py extract-pdf book.pdf "0,266-273" --zero-based  # 0-based indices (pages 1, 267-274)
./mcp_fuzzy_search.py extract-pdf book.pdf "1-50" --one-based  # 1-based indices (pages 1-50)

# Get PDF information
./mcp_fuzzy_search.py page-labels manual.pdf  # List all page labels
./mcp_fuzzy_search.py page-labels manual.pdf --start 100 --limit 20  # Get labels for pages 100-119
./mcp_fuzzy_search.py page-count manual.pdf  # Get total page count
./mcp_fuzzy_search.py pdf-outline manual.pdf  # Get table of contents
./mcp_fuzzy_search.py pdf-outline manual.pdf --max-depth 2  # Limit to 2 levels
./mcp_fuzzy_search.py pdf-outline manual.pdf --fuzzy-filter "chapter"  # Filter by title
./mcp_fuzzy_search.py pdf-outline manual.pdf --no-simple  # Detailed output with links
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

Both MCP servers support **multiline search mode** which changes the search behavior:

### What is Multiline Mode?

**Default behavior (multiline=false):**
- **File Search Server**: Searches file NAMES/PATHS only
- **Fuzzy Search Server**: Searches line-by-line within file contents

**With multiline mode (multiline=true):**
- **File Search Server**: Switches to searching file CONTENTS instead of names
- **Fuzzy Search Server**: Treats entire file contents as single searchable units

### When to Use Multiline Mode

Multiline mode is for searching file CONTENTS (not names):
- **Finding class definitions** with their methods: `"class UserService authenticate"` (fuzzy match in contents)
- **Locating function implementations**: `"async function await fetch"` (all terms in one file)
- **Searching for configuration blocks**: `"database host port"` (finds files containing all terms)
- **Finding code structures** across lines: `"try catch finally"` (fuzzy matches across lines)
- **Important**: This searches CONTENTS, not file names!

### Multiline Examples

#### File Search Server Multiline (Content Search)
```bash
# With --multiline, searches file CONTENTS instead of names
# Find files CONTAINING these terms (not in file names)
./mcp_fd_server.py filter "class constructor method" "" src --multiline

# Find Python files CONTAINING specific patterns  
./mcp_fd_server.py filter "class def return" "" . --multiline

# Find files CONTAINING database configuration
./mcp_fd_server.py filter "database host password" "" config --multiline
```

#### Fuzzy Search Server Multiline
```bash
# search-files with --multiline searches file CONTENTS (not names)
./mcp_fuzzy_search.py search-files "async function await" src --multiline

# search-content with --multiline treats files as single units
./mcp_fuzzy_search.py search-content "try catch finally" . --multiline

# Find files CONTAINING class definitions with specific methods
./mcp_fuzzy_search.py search-content "class constructor render" src --multiline
```

### Performance Considerations

- **File size**: Multiline mode reads entire files into memory; best for typical source code files
- **Result size**: Multiline results include complete file contents, which may be truncated for display
- **Pattern complexity**: Simple fuzzy patterns work well; complex queries may be slower

### Tips for Multiline Queries

1. **Use specific terms**: `"class MyClass def method"` is better than just `"class def"` (no regex!)
2. **Combine structure and content**: `"import React export default"` finds React components
3. **Mind the output**: Results show the entire matching file content
4. **Test incrementally**: Start with simple patterns and refine

## fzf Search Syntax Guide

Both MCP servers use **fzf's extended search syntax** for powerful fuzzy filtering. Understanding this syntax will help you construct precise queries.

**IMPORTANT**: The `fuzzy_filter` parameter in `fuzzy_search_content` does NOT support regular expressions. It uses fzf's fuzzy matching syntax as described below. If you need regex-like patterns, use the position anchors and exact matching features of fzf syntax instead.

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

**Note**: These examples show how to achieve regex-like filtering WITHOUT using regular expressions, since `fuzzy_filter` does not support regex.

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

**Default Mode (matches file paths AND content):**
```bash
# Find implementation TODOs in specific file types
TODO implement .py: | .js:  # Matches TODO in .py or .js files

# Find error handling in specific files
error 'main.py:' | 'app.js:'  # Matches 'error' in main.py or app.js

# Find updates in test files
test.py: update  # Matches 'update' in files named test.py

# Find async functions with error handling
'async def' error .py$  # Matches in Python files
```

**Content-Only Mode (ignores file paths):**
```bash
# With --content-only flag or content_only=true parameter
# These will ONLY match the content, not file names:

# Find TODO comments regardless of filename
TODO implement  # Won't match files named 'TODO.txt'

# Find async/await patterns
async await catch  # Pure content search

# Find class definitions
'class ' 'def __init__'  # Won't match 'class.py' filename
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
Find files by NAME using fd with regex or glob patterns.

**Purpose:** Search for files when you know exact patterns, extensions, or regex for file NAMES.

**Parameters:**
- `pattern` (required): Regex or glob pattern to match file names
- `path` (optional): Directory to search in (defaults to current directory)
- `flags` (optional): Additional flags to pass to fd

**Example:**
```python
{
  "pattern": r"\.py$",  # Find files with names ending in .py
  "path": "/home/user/projects",
  "flags": "--hidden --no-ignore"
}
```

#### `filter_files`
Fuzzy search for files by NAME using fzf's fuzzy matching.

**Purpose:** Find files when you only know partial or approximate file NAMES.

**Parameters:**
- `filter` (required): Fuzzy search string to match against file names/paths
- `pattern` (optional): Initial pattern for fd to pre-filter
- `path` (optional): Directory to search in
- `first` (optional): Return only the best match
- `fd_flags` (optional): Extra flags for fd
- `fzf_flags` (optional): Extra flags for fzf
- `multiline` (optional): When true, searches file CONTENTS instead of names (default: false)

**Example (File Name Search):**
```python
{
  "filter": "test",  # Fuzzy match 'test' in file names
  "pattern": r"\.py$",  # Only Python files
  "path": "./src",
  "first": true
}
```

**Multiline Example (Content Search):**
```python
{
  "filter": "class function return",  # Find files containing all these terms
  "pattern": "",
  "path": "./src",
  "multiline": true  # Search CONTENTS, not names
}
```

### Fuzzy Search Server Tools

#### `fuzzy_search_files`
Search for file NAMES/PATHS using fuzzy matching.

**Purpose:** Find files by NAME when you only know partial names (e.g., "mainpy" finds "main.py").

**Parameters:**
- `fuzzy_filter` (required): Fuzzy search string for file names/paths
- `path` (optional): Directory to search in (defaults to current directory)
- `hidden` (optional): Include hidden files (default: false)
- `limit` (optional): Maximum results to return (default: 20)
- `multiline` (optional): When true, searches file CONTENTS instead of names (default: false)
- `confirm_root` (optional): Allow searching from root directory (/) (default: false)

**Example (File Name Search):**
```python
{
  "fuzzy_filter": "main",  # Finds main.py, main.js, domain.py, etc.
  "path": "/home/user/projects",
  "hidden": true,
  "limit": 10
}
```

**Multiline Example (Content Search):**
```python
{
  "fuzzy_filter": "import export",  # Find files containing both terms
  "path": "./src",
  "multiline": true,  # Search CONTENTS, not names
  "limit": 5
}
```

#### `fuzzy_search_content`
Search file contents with fuzzy filtering, matching on BOTH file paths AND content by default.

**Purpose:** Find specific text/code using fuzzy search that considers both where it is (path) and what it is (content).

**Parameters:**
- `fuzzy_filter` (required): Fuzzy search query for filtering (does NOT support regex - use fzf syntax)
- `path` (optional): Directory/file to search in (defaults to current directory)
- `hidden` (optional): Search hidden files (default: false)
- `limit` (optional): Maximum results to return (default: 20)
- `rg_flags` (optional): Extra flags for ripgrep (see ripgrep flags reference)
- `multiline` (optional): Enable multiline record processing (default: false)
- `content_only` (optional): Match ONLY on content, ignore file paths (default: false)
- `confirm_root` (optional): Allow searching from root directory (/) (default: false)

**Matching Behavior:**
- **Default (content_only=false)**: Matches on BOTH file paths AND content (skips line numbers)
  - This is why `"test.py: update"` finds "update" in test.py files - it matches the path!
  - Searching `"src TODO"` finds TODO comments in files under src/ directory
  - Even just `"update"` will match files named "update.py" OR containing "update"
- **With content_only=true**: Matches ONLY on content, ignoring file paths entirely
  - Pure content search - `"update"` won't match "update.py" filename, only content

**Example (Default - Path + Content):**
```python
{
  "fuzzy_filter": "test.py: TODO implement",  # Find TODOs in test.py files
  "path": "./src",
  "rg_flags": "-i",
  "limit": 15
}
```

**Example (Content Only):**
```python
{
  "fuzzy_filter": "async await catch",  # Find these terms in content only
  "path": "./src",
  "content_only": true,  # Ignore file paths in matching
  "limit": 10
}
```

#### `fuzzy_search_documents`
Search through PDFs and other document formats using ripgrep-all (requires optional binaries).

**Purpose:** Search PDFs, Office documents, archives, and other binary formats that regular text search can't handle.

**Parameters:**
- `fuzzy_filter` (required): Fuzzy search query for document content
- `path` (optional): Directory/file to search in (defaults to current directory)
- `file_types` (optional): Comma-separated file types to search (e.g., "pdf,docx,epub")
- `preview` (optional): Include preview context (default: true)
- `limit` (optional): Maximum results to return (default: 20)
- `confirm_root` (optional): Allow searching from root directory (/) (default: false)

**Example:**
```python
{
  "fuzzy_filter": "machine learning algorithm",
  "path": "./research",
  "file_types": "pdf,epub",
  "limit": 10
}
```

**Returns:**
```python
{
  "matches": [
    {
      "file": "/path/to/document.pdf",
      "line": 0,
      "content": "topology.",  # Content without "Page N: " prefix
      "match_text": "topology",
      "page": 542,  # 1-based page number (from ripgrep-all)
      "page_index_0based": 541,  # 0-based page index for programmatic access
      "page_label": "19"  # Actual PDF page label (only for PDFs with PyMuPDF)
    }
  ]
}
```

**Note:** For PDF files, the tool returns:
- `page`: The 1-based page number from ripgrep-all (e.g., 542 means the 542nd page)
- `page_index_0based`: The 0-based page index for programmatic access (e.g., 541 for page 542)
- `page_label`: The actual page label as shown in PDF readers (e.g., "vii", "ToC", "19")

The content field no longer includes the "Page N: " prefix for cleaner output.

#### `extract_pdf_pages`
Extract specific pages from a PDF and convert to various formats using PyMuPDF.

**Purpose:** Extract individual pages or page ranges from PDFs with support for page labels/aliases as they appear in PDF readers.

**Parameters:**
- `file` (required): Path to PDF file
- `pages` (required): Comma-separated page specifications - supports:
  - Page labels: "v", "vii", "ToC", "Introduction" (as shown in PDF readers)
  - Page ranges: "v-vii", "1-5"
  - Physical pages: "1", "14" (1-based if not found as label)
  - Mixed: "v,vii,1,5-8,ToC"
- `format` (optional): Output format - markdown, html, plain (default: markdown)
- `preserve_layout` (optional): Try to preserve original layout (default: false)
- `clean_html` (optional): Strip HTML styling tags like `<span style="...">` (default: true)
- `fuzzy_hint` (optional): Fuzzy search string to filter extracted pages by content
- `zero_based` (optional): Interpret page numbers as 0-based indices (default: false)
  - When true, all numbers are treated as direct 0-based page indices
  - "0" = first page, "266" = 267th page, "0-4" = first 5 pages
  - No page label lookup is performed when this is true
  - Cannot be used together with `one_based`
- `one_based` (optional): Interpret page numbers as 1-based indices (default: false)
  - When true, all numbers are treated as direct 1-based page indices
  - "1" = first page, "267" = 267th page, "1-5" = first 5 pages
  - No page label lookup is performed when this is true
  - Cannot be used together with `zero_based`

**Example:**
```python
{
  "file": "research_paper.pdf",
  "pages": "v-vii,1,5-10,ToC",  # Mix of page labels and numbers
  "format": "markdown",
  "clean_html": true,
  "fuzzy_hint": "neural network"  # Only include pages mentioning this
}

# Example with zero_based=true
{
  "file": "research_paper.pdf",
  "pages": "0,266-273",  # Direct 0-based indices: page 1 and pages 267-274
  "zero_based": true
}

# Example with one_based=true
{
  "file": "research_paper.pdf",
  "pages": "1,267-274",  # Direct 1-based indices: pages 1, 267-274
  "one_based": true
}
```

#### `get_pdf_page_labels`
Get all page labels from a PDF file.

**Purpose:** Returns a mapping of page indices to their labels/aliases as shown in PDF readers, helpful for understanding available page labels before extraction.

**Parameters:**
- `file` (required): Path to PDF file
- `start` (optional): 0-based start index for slicing results (default: 0)
- `limit` (optional): Maximum number of labels to return (default: all pages)

**Example:**
```python
{
  "file": "research_paper.pdf"
}

# Returns something like:
{
  "page_labels": {
    "0": "Cover",
    "1": "i",
    "2": "ii", 
    "3": "iii",
    "4": "iv",
    "5": "v",
    "6": "vi",
    "7": "vii",
    "8": "viii",
    "9": "1",
    "10": "2",
    "11": "3"
  },
  "page_count": 150
}

# Example with slicing:
{
  "file": "research_paper.pdf",
  "start": 100,
  "limit": 20
}

# Returns subset like:
{
  "page_labels": {
    "100": "87",
    "101": "88",
    "102": "89",
    "103": "90",
    "104": "91"
    # ... up to 20 entries
  },
  "page_count": 150
}
```

#### `get_pdf_page_count`
Get the total number of pages in a PDF file.

**Purpose:** Returns the total page count, useful for understanding the document size before extraction.

**Parameters:**
- `file` (required): Path to PDF file

**Example:**
```python
{
  "file": "research_paper.pdf"
}

# Returns:
{
  "page_count": 150
}
```

#### `get_pdf_outline`
Extract the table of contents (outline/bookmarks) from a PDF file.

**Purpose:** Returns the hierarchical outline structure with levels, titles, page numbers, and page labels, helpful for navigating complex PDFs and understanding document structure.

**Parameters:**
- `file` (required): Path to PDF file
- `simple` (optional): Return basic info (default: true) or detailed info with link data (false)
- `max_depth` (optional): Maximum depth to traverse in the outline hierarchy (default: unlimited)
- `fuzzy_filter` (optional): Fuzzy search string to filter outline entries by title using fzf

**Example:**
```python
{
  "file": "research_paper.pdf"
}

# Returns (simple mode):
{
  "outline": [
    [1, "Introduction", 1, "i"],
    [1, "Chapter 1: Background", 5, "1"],
    [2, "1.1 History", 6, "2"],
    [2, "1.2 Related Work", 10, "6"],
    [1, "Chapter 2: Methods", 15, "11"],
    [2, "2.1 Data Collection", 16, "12"],
    [3, "2.1.1 Sources", 17, "13"],
    [2, "2.2 Analysis", 20, "16"]
  ],
  "total_entries": 8,
  "max_depth_found": 3
}

# Example with filtering:
{
  "file": "research_paper.pdf",
  "fuzzy_filter": "chapter"
}

# Returns:
{
  "outline": [
    [1, "Chapter 1: Background", 5, "1"],
    [1, "Chapter 2: Methods", 15, "11"]
  ],
  "total_entries": 8,
  "max_depth_found": 3,
  "filtered_count": 2
}

# Example with detailed output:
{
  "file": "research_paper.pdf",
  "simple": false,
  "max_depth": 2
}

# Returns:
{
  "outline": [
    [1, "Introduction", 1, "i", {
      "page": 1,
      "uri": "#page=1&zoom=100,0,0",
      "is_external": false,
      "is_open": true,
      "dest": {
        "kind": 1,
        "page": 0,
        "uri": "#page=1&zoom=100,0,0"
      }
    }],
    # ... more entries with link details
  ],
  "total_entries": 8,
  "max_depth_found": 2
}
```

**Outline Format:**
- Simple mode returns: `[level, title, page, page_label]`
  - `level`: Hierarchy level (1-based, 1 = top level)
  - `title`: The bookmark/outline entry title
  - `page`: Page number (1-based)
  - `page_label`: Page label as shown in PDF readers (e.g., "i", "ii", "1", "ToC")
- Detailed mode adds a 5th element with link information including destination details

### SQLite Server Tools

#### `query`
Execute SELECT queries on the database.

**Parameters:**
- `query` (required): SELECT query to execute
- `db_path` (optional): Path to SQLite database (defaults to configured db_path or ':memory:')

**Example:**
```python
{
  "query": "SELECT * FROM users WHERE active = 1 ORDER BY created_at DESC LIMIT 10",
  "db_path": "myapp.db"
}
```

#### `execute`
Execute INSERT, UPDATE, or DELETE queries (requires write permissions).

**Parameters:**
- `query` (required): INSERT, UPDATE, or DELETE query to execute
- `db_path` (optional): Path to SQLite database

**Example:**
```python
{
  "query": "UPDATE users SET last_login = datetime('now') WHERE id = 123",
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

### Root Path Protection
- **Built-in safety mechanism**: All search functions prevent accidental searches from root directory (/) by default
- Searching from root without explicit confirmation returns an error message
- To search from root directory, you must explicitly set `confirm_root=True` (MCP tools) or use `--confirm-root` flag (CLI)
- This prevents unintended performance issues and excessive filesystem access
- Cross-platform support: protects against both Unix root (/) and Windows drive roots (C:\, etc.)

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

### "Searching from root directory (/) is likely incorrect and could be very slow"
- This safety message appears when trying to search from the root directory without explicit confirmation
- To search from root, add `confirm_root=True` parameter (MCP tools) or `--confirm-root` flag (CLI)
- Consider using a more specific directory path instead for better performance
- Example: `./mcp_fuzzy_search.py search-files "config" / --confirm-root`

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
- [PyMuPDF](https://github.com/pymupdf/PyMuPDF) - Python bindings for MuPDF for PDF processing (optional)
- [ripgrep-all](https://github.com/phiresky/ripgrep-all) - ripgrep, but also search in PDFs, E-Books, Office documents (optional)
- [pandoc](https://pandoc.org/) - Universal markup converter (optional)

### SQLite Server
- [SQLite](https://www.sqlite.org/) - Self-contained, serverless, zero-configuration SQL database engine