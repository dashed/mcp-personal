"""Simplified tests for mcp_fd_server using direct function calls."""
import shutil
import pytest
from pathlib import Path
from unittest.mock import patch
import json
import mcp_fd_server


def test_search_files_direct():
    """Test search_files function directly."""
    # Skip if fd not available
    if not mcp_fd_server.FD_EXECUTABLE:
        pytest.skip("fd not available")
    
    # Use current directory for simple test
    result = mcp_fd_server.search_files(pattern=r"\.py$", path=".")
    
    # Should return a dict with matches key
    assert isinstance(result, dict)
    assert "matches" in result or "error" in result
    
    if "matches" in result:
        assert isinstance(result["matches"], list)
        # Should find at least mcp_fd_server.py itself
        assert any("mcp_fd_server.py" in match for match in result["matches"])


def test_search_files_error():
    """Test search_files error handling."""
    result = mcp_fd_server.search_files(pattern="")
    
    assert result == {"error": "'pattern' argument is required"}


def test_filter_files_direct():
    """Test filter_files function directly."""
    # Skip if dependencies not available
    if not mcp_fd_server.FD_EXECUTABLE or not mcp_fd_server.FZF_EXECUTABLE:
        pytest.skip("fd or fzf not available")
    
    # Search for python files containing "test"
    result = mcp_fd_server.filter_files(filter="test", pattern=r"\.py$", path=".")
    
    assert isinstance(result, dict)
    assert "matches" in result or "error" in result


def test_filter_files_error():
    """Test filter_files error handling."""
    result = mcp_fd_server.filter_files(filter="")
    
    assert result == {"error": "'filter' argument is required"}


@patch("subprocess.check_output")
def test_search_files_mocked(mock_check_output):
    """Test search_files with mocked subprocess."""
    mock_check_output.return_value = "src/main.py\nsrc/test.py\n"
    
    with patch.object(mcp_fd_server, "FD_EXECUTABLE", "/mock/fd"):
        result = mcp_fd_server.search_files(pattern=r"\.py$", path="src")
    
    assert result["matches"] == ["src/main.py", "src/test.py"]


def test_binary_missing_exception():
    """Test BinaryMissing exception."""
    with pytest.raises(mcp_fd_server.BinaryMissing) as exc_info:
        mcp_fd_server._require(None, "test-binary")
    
    assert "Cannot find the `test-binary` binary" in str(exc_info.value)


def test_cli_functionality(tmp_path):
    """Test CLI helper functionality."""
    # Create test file
    test_file = tmp_path / "test.py"
    test_file.write_text("print('hello')")
    
    # Skip if fd not available
    if not mcp_fd_server.FD_EXECUTABLE:
        pytest.skip("fd not available")
    
    # Test search functionality
    result = mcp_fd_server.search_files(pattern=r"\.py$", path=str(tmp_path))
    
    assert "matches" in result
    assert str(test_file) in result["matches"]