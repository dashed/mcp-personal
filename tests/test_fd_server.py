import shutil
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
import mcp_fd_server
from mcp.shared.memory import create_connected_server_and_client_session as client_session

pytestmark = pytest.mark.anyio


def _skip_if_missing(binary: str):
    """Skip test if binary is not available on PATH."""
    if shutil.which(binary) is None:
        pytest.skip(f"{binary} not on PATH")


async def test_search_files_finds_python(tmp_path: Path):
    """Test that search_files correctly finds Python files."""
    _skip_if_missing("fd")
    
    # Arrange
    (tmp_path / "one.py").write_text("print('hi')")
    (tmp_path / "two.txt").write_text("hello")
    (tmp_path / "subdir").mkdir()
    (tmp_path / "subdir" / "three.py").write_text("# python file")
    
    # Act
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "search_files",
            {"pattern": r"\.py$", "path": str(tmp_path)}
        )
    
        # Assert
        assert hasattr(result, 'content')
        assert len(result.content) > 0
        content = result.content[0]
        assert content.type == "text"
        import json
        data = json.loads(content.text)
        assert "matches" in data
        assert str(tmp_path / "one.py") in data["matches"]
        assert str(tmp_path / "subdir" / "three.py") in data["matches"]
        assert all(p.endswith(".py") for p in data["matches"])
        assert str(tmp_path / "two.txt") not in data["matches"]


async def test_search_files_with_flags(tmp_path: Path):
    """Test search_files with additional fd flags."""
    _skip_if_missing("fd")
    
    # Arrange
    (tmp_path / ".hidden.py").write_text("# hidden")
    (tmp_path / "visible.py").write_text("# visible")
    
    # Act without hidden flag
    import json
    
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result_no_hidden = await client.call_tool(
            "search_files",
            {"pattern": r"\.py$", "path": str(tmp_path)}
        )
        data_no_hidden = json.loads(result_no_hidden.content[0].text)
        
        # Act with hidden flag
        result_with_hidden = await client.call_tool(
            "search_files",
            {"pattern": r"\.py$", "path": str(tmp_path), "flags": "--hidden"}
        )
        data_with_hidden = json.loads(result_with_hidden.content[0].text)
        
        # Assert
        assert str(tmp_path / "visible.py") in data_no_hidden["matches"]
        assert str(tmp_path / ".hidden.py") not in data_no_hidden["matches"]
        assert str(tmp_path / ".hidden.py") in data_with_hidden["matches"]


async def test_search_files_error_handling():
    """Test search_files error handling for missing pattern."""
    import json
    
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "search_files",
            {"pattern": ""}
        )
        
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert "'pattern' argument is required" in data["error"]


async def test_filter_files_returns_best_match(tmp_path: Path):
    """Test filter_files with fuzzy matching."""
    _skip_if_missing("fd")
    _skip_if_missing("fzf")
    
    # Arrange
    (tmp_path / "main.rs").write_text("// rust")
    (tmp_path / "minor.rs").write_text("// rust")
    (tmp_path / "maintenance.rs").write_text("// rust")
    
    # Act
    import json
    
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "filter_files",
            {
                "filter": "main",
                "pattern": r"\.rs$",
                "path": str(tmp_path),
                "first": True
            }
        )
        
        # Assert
        data = json.loads(result.content[0].text)
        assert "matches" in data
        assert len(data["matches"]) == 1
        assert data["matches"][0] == str(tmp_path / "main.rs")


async def test_filter_files_multiple_matches(tmp_path: Path):
    """Test filter_files returning multiple fuzzy matches."""
    _skip_if_missing("fd")
    _skip_if_missing("fzf")
    
    # Arrange
    (tmp_path / "config.json").write_text("{}")
    (tmp_path / "configuration.yaml").write_text("key: value")
    (tmp_path / "settings.toml").write_text("[section]")
    
    # Act
    import json
    
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "filter_files",
            {
                "filter": "conf",
                "path": str(tmp_path)
            }
        )
        
        # Assert
        data = json.loads(result.content[0].text)
        assert "matches" in data
        assert any("config" in p for p in data["matches"])


async def test_filter_files_error_handling():
    """Test filter_files error handling for missing filter."""
    import json
    
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "filter_files",
            {"filter": ""}
        )
        
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert "'filter' argument is required" in data["error"]


async def test_list_tools():
    """Test that tools are properly exposed with correct metadata."""
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.list_tools()
        
        # Should have exactly 2 tools
        assert len(result.tools) == 2
        
        # Find tools by name
        search_tool = next(t for t in result.tools if t.name == "search_files")
        filter_tool = next(t for t in result.tools if t.name == "filter_files")
        
        # Verify search_files metadata
        assert search_tool.description.startswith("Find files using *fd*")
        assert "pattern" in search_tool.inputSchema["required"]
        
        # Verify filter_files metadata
        assert filter_tool.description.startswith("Run fd, then fuzzy")
        assert "filter" in filter_tool.inputSchema["required"]


@patch("shutil.which")
def test_binary_discovery(mock_which):
    """Test binary discovery logic."""
    # Store original values
    original_fd = mcp_fd_server.FD_EXECUTABLE
    original_fzf = mcp_fd_server.FZF_EXECUTABLE
    
    try:
        # Test when fd is available as 'fd'
        mock_which.side_effect = lambda x: "/usr/bin/fd" if x == "fd" else None
        
        # Reload module to trigger discovery
        import importlib
        importlib.reload(mcp_fd_server)
        
        assert mcp_fd_server.FD_EXECUTABLE == "/usr/bin/fd"
        
        # Test when fd is available as 'fdfind' (Debian/Ubuntu)
        mock_which.side_effect = lambda x: "/usr/bin/fdfind" if x == "fdfind" else None
        importlib.reload(mcp_fd_server)
        
        assert mcp_fd_server.FD_EXECUTABLE == "/usr/bin/fdfind"
    finally:
        # Restore original values
        mcp_fd_server.FD_EXECUTABLE = original_fd
        mcp_fd_server.FZF_EXECUTABLE = original_fzf


def test_require_binary():
    """Test the _require helper function."""
    # Valid binary
    assert mcp_fd_server._require("/usr/bin/fd", "fd") == "/usr/bin/fd"
    
    # Missing binary
    with pytest.raises(mcp_fd_server.BinaryMissing) as exc_info:
        mcp_fd_server._require(None, "fd")
    
    assert "Cannot find the `fd` binary" in str(exc_info.value)


@patch("subprocess.check_output")
async def test_search_files_mocked(mock_check_output):
    """Test search_files with mocked subprocess for CI environments."""
    # Mock fd output
    mock_check_output.return_value = "src/main.py\nsrc/test.py\n"
    
    # Override binary check
    import json
    
    with patch.object(mcp_fd_server, "FD_EXECUTABLE", "/mock/fd"):
        async with client_session(mcp_fd_server.mcp._mcp_server) as client:
            result = await client.call_tool(
                "search_files",
                {"pattern": r"\.py$", "path": "src"}
            )
        
            # Assert
            data = json.loads(result.content[0].text)
            assert data["matches"] == ["src/main.py", "src/test.py"]
            mock_check_output.assert_called_once()


@patch("subprocess.Popen")
@patch("subprocess.check_output")
async def test_filter_files_mocked(mock_check_output, mock_popen):
    """Test filter_files with mocked subprocess for CI environments."""
    # Mock fd process
    fd_proc = MagicMock()
    fd_proc.stdout = MagicMock()
    mock_popen.return_value = fd_proc
    
    # Mock fzf output
    mock_check_output.return_value = "src/main.py\n"
    
    # Override binary checks
    import json
    
    with patch.object(mcp_fd_server, "FD_EXECUTABLE", "/mock/fd"), \
         patch.object(mcp_fd_server, "FZF_EXECUTABLE", "/mock/fzf"):
        async with client_session(mcp_fd_server.mcp._mcp_server) as client:
            result = await client.call_tool(
                "filter_files",
                {"filter": "main", "pattern": r"\.py$"}
            )
        
            # Assert
            data = json.loads(result.content[0].text)
            assert data["matches"] == ["src/main.py"]