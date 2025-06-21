# MCP FD Server Tests

This directory contains tests for the MCP FD Server implementation.

## Test Structure

- `test_simple.py` - Direct function tests that don't require MCP client/server setup
- `test_fd_server.py` - Full integration tests using MCP client/server protocol
- `test_cli.py` - CLI interface tests
- `conftest.py` - Shared pytest fixtures for MCP client setup

## Running Tests

### Simple Tests (Recommended)
Run the simplified tests that directly test the tool functions:

```bash
# Using uv (recommended)
PYTHONPATH=. uv run --with pytest --with mcp pytest tests/test_simple.py -v

# Or run all tests
PYTHONPATH=. uv run --with pytest --with mcp pytest tests/ -v
```

### Full Integration Tests
The full integration tests require more setup and use the MCP client/server protocol:

```bash
# Disable plugin autoload if you encounter issues
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD="" uv run --with pytest --with pytest-asyncio --with mcp pytest tests/test_fd_server.py -v
```

## Test Coverage

The tests cover:
- Basic functionality of `search_files` and `filter_files` tools
- Error handling for missing arguments
- Binary discovery and fallback mechanisms
- CLI interface functionality
- Mocked tests for CI environments without fd/fzf installed

## CI/CD Considerations

Tests that require `fd` and `fzf` binaries will be automatically skipped if these tools are not available on the system. The test suite includes mocked versions of these tests that can run in CI environments.

## Dependencies

Test dependencies are specified in the script header:
- pytest>=7.0
- pytest-asyncio>=0.21.0 (for full integration tests)
- mcp>=0.1.0

Install with:
```bash
uv run --extra dev pytest
```