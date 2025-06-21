# MCP FD Server Tests

This directory contains tests for the MCP FD Server implementation.

## Test Structure

- `test_simple.py` - Direct function tests that don't require MCP client/server setup
- `test_fd_server.py` - Full integration tests using MCP client/server protocol
- `test_cli.py` - CLI interface tests
- `conftest.py` - Shared pytest fixtures for MCP client setup

## Running Tests

### All Tests
Run the complete test suite:

```bash
# Using uv (recommended)
make test

# Or directly with pytest
PYTHONPATH=. uv run pytest tests/ -v
```

### Specific Test Categories
```bash
# Simple/direct function tests only
make test-simple

# Full MCP integration tests only  
make test-full

# CLI tests only
make test-cli
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

## Test Results

The test suite includes:
- 7 simple function tests
- 20 async MCP integration tests (10 asyncio + 10 trio variants)
- 7 CLI tests (3 skipped by default)

All tests are passing with the current implementation.

## Dependencies

Test dependencies are specified in the script header:
- pytest>=7.0
- pytest-asyncio>=0.21.0 (for full integration tests)
- mcp>=0.1.0

Install with:
```bash
uv run --extra dev pytest
```