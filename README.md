# MCP Personal - Collection of Personal MCP Servers

A collection of [Model Context Protocol](https://modelcontextprotocol.io) (MCP) servers for various personal productivity tools and utilities.

## Available MCP Servers

### 1. File Search Server (`mcp_fd_server.py`)
Powerful file search capabilities using `fd` and `fzf`:
- **Fast file search** using `fd` (a modern, user-friendly alternative to `find`)
- **Fuzzy filtering** with `fzf` for intelligent file matching
- **Regex and glob pattern** support
- **Standalone CLI** for testing and direct usage

### More servers coming soon...
This repository will grow to include additional MCP servers for various tasks.

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

## Installation

### Clone the Repository

```bash
git clone https://github.com/yourusername/mcp-personal.git
cd mcp-personal
```

### Configure MCP Servers

Each server can be configured independently in Claude Desktop. Add the desired servers to `~/Library/Application Support/Claude/claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "file-search": {
      "command": "/path/to/mcp-personal/mcp_fd_server.py"
    }
    // Add more servers here as they become available
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

**Example:**
```python
{
  "filter": "test",
  "pattern": r"\.py$",
  "path": "./src",
  "first": true
}
```

## Development

### Project Structure
```
mcp-personal/
├── mcp_fd_server.py      # File search MCP server
├── tests/                # Test suite
│   ├── test_simple.py    # Direct function tests
│   ├── test_fd_server.py # MCP integration tests
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

## Security Considerations

### General
- All servers run with the permissions of the user executing them
- Consider the security implications of each server's capabilities
- Review server code before installation

### File Search Server
- Has filesystem access based on user permissions
- Be cautious when searching in sensitive directories
- The `--no-ignore` flag will include files normally hidden by `.gitignore`

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