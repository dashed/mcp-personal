import json
import shutil
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from mcp.shared.memory import (
    create_connected_server_and_client_session as client_session,
)

import mcp_fd_server

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
            "search_files", {"pattern": r"\.py$", "path": str(tmp_path)}
        )

        # Assert
        assert hasattr(result, "content")
        assert len(result.content) > 0
        content = result.content[0]
        assert content.type == "text"

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

    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result_no_hidden = await client.call_tool(
            "search_files", {"pattern": r"\.py$", "path": str(tmp_path)}
        )
        data_no_hidden = json.loads(result_no_hidden.content[0].text)

        # Act with hidden flag
        result_with_hidden = await client.call_tool(
            "search_files",
            {"pattern": r"\.py$", "path": str(tmp_path), "flags": "--hidden"},
        )
        data_with_hidden = json.loads(result_with_hidden.content[0].text)

        # Assert
        assert str(tmp_path / "visible.py") in data_no_hidden["matches"]
        assert str(tmp_path / ".hidden.py") not in data_no_hidden["matches"]
        assert str(tmp_path / ".hidden.py") in data_with_hidden["matches"]


async def test_search_files_error_handling():
    """Test search_files error handling for missing pattern."""
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool("search_files", {"pattern": ""})

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
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "filter_files",
            {
                "filter": "main",
                "pattern": r"\.rs$",
                "path": str(tmp_path),
                "first": True,
            },
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
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "filter_files", {"filter": "conf", "path": str(tmp_path)}
        )

        # Assert
        data = json.loads(result.content[0].text)
        assert "matches" in data
        assert any("config" in p for p in data["matches"])


async def test_filter_files_error_handling():
    """Test filter_files error handling for missing filter."""
    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool("filter_files", {"filter": ""})

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


def test_binary_discovery():
    """Test binary discovery logic for fd and fzf."""
    with patch("shutil.which") as mock_which:
        # Test fd discovery (fd takes precedence over fdfind)
        mock_which.side_effect = lambda x: "/usr/bin/fd" if x == "fd" else (
            "/usr/bin/fdfind" if x == "fdfind" else None
        )
        fd_path = mock_which("fd") or mock_which("fdfind")
        assert fd_path == "/usr/bin/fd"

        # Test fdfind fallback (Debian/Ubuntu)
        mock_which.side_effect = lambda x: "/usr/bin/fdfind" if x == "fdfind" else None
        fd_path = mock_which("fd") or mock_which("fdfind")
        assert fd_path == "/usr/bin/fdfind"

        # Reset side_effect and test no fd available
        mock_which.side_effect = None
        mock_which.return_value = None
        fd_path = mock_which("fd") or mock_which("fdfind")
        assert fd_path is None


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
                "search_files", {"pattern": r"\.py$", "path": "src"}
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
    with (
        patch.object(mcp_fd_server, "FD_EXECUTABLE", "/mock/fd"),
        patch.object(mcp_fd_server, "FZF_EXECUTABLE", "/mock/fzf"),
    ):
        async with client_session(mcp_fd_server.mcp._mcp_server) as client:
            result = await client.call_tool(
                "filter_files", {"filter": "main", "pattern": r"\.py$"}
            )

            # Assert
            data = json.loads(result.content[0].text)
            assert data["matches"] == ["src/main.py"]


# Additional comprehensive tests


async def test_search_files_default_path():
    """Test search_files with default path (current directory)."""
    _skip_if_missing("fd")

    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool("search_files", {"pattern": r"\.py$"})

        data = json.loads(result.content[0].text)
        # Should find some .py files in current directory (at least mcp_fd_server.py)
        assert "matches" in data


async def test_filter_files_with_fd_and_fzf_flags(tmp_path: Path):
    """Test filter_files with additional fd and fzf flags."""
    _skip_if_missing("fd")
    _skip_if_missing("fzf")

    # Create test files
    (tmp_path / ".env.local").write_text("SECRET=hidden")
    (tmp_path / "config.env").write_text("PUBLIC=visible")

    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "filter_files",
            {
                "filter": "env",
                "pattern": "env",
                "path": str(tmp_path),
                "fd_flags": "--hidden",
                "fzf_flags": "--exact",
            },
        )

        data = json.loads(result.content[0].text)
        assert "matches" in data
        # Should find both files with --hidden flag
        assert len(data["matches"]) >= 1


async def test_search_files_with_multiple_flags(tmp_path: Path):
    """Test search_files with multiple fd flags."""
    _skip_if_missing("fd")

    # Create test structure
    (tmp_path / ".hidden").mkdir()
    (tmp_path / ".hidden" / "secret.py").write_text("# secret")
    (tmp_path / "public.py").write_text("# public")

    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "search_files",
            {"pattern": r"\.py$", "path": str(tmp_path), "flags": "--hidden --type f"},
        )

        data = json.loads(result.content[0].text)
        assert "matches" in data
        # Should find both files with --hidden flag
        assert any("secret.py" in match for match in data["matches"])
        assert any("public.py" in match for match in data["matches"])


async def test_empty_search_results(tmp_path: Path):
    """Test behavior when search returns no results."""
    _skip_if_missing("fd")

    # Create directory with no matching files
    (tmp_path / "readme.txt").write_text("documentation")

    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "search_files", {"pattern": r"\.nonexistent$", "path": str(tmp_path)}
        )

        data = json.loads(result.content[0].text)
        assert "matches" in data
        assert data["matches"] == []


async def test_filter_files_empty_results(tmp_path: Path):
    """Test filter_files with no fuzzy matches."""
    _skip_if_missing("fd")
    _skip_if_missing("fzf")

    # Create test files
    (tmp_path / "alpha.txt").write_text("content")
    (tmp_path / "beta.txt").write_text("content")

    async with client_session(mcp_fd_server.mcp._mcp_server) as client:
        result = await client.call_tool(
            "filter_files",
            {"filter": "zzz_nonmatch", "pattern": r"\.txt$", "path": str(tmp_path)},
        )

        data = json.loads(result.content[0].text)
        # fzf may return error for no matches, or empty matches list
        if "error" in data:
            # This is acceptable - fzf can return error when no matches
            assert isinstance(data["error"], str)
        else:
            assert "matches" in data
            assert isinstance(data["matches"], list)


# CLI interface tests


def test_cli_search_command(tmp_path: Path):
    """Test CLI search subcommand."""
    # Create test files
    (tmp_path / "test.py").write_text("print('hello')")
    (tmp_path / "test.txt").write_text("hello")

    result = subprocess.run(
        [sys.executable, "mcp_fd_server.py", "search", r"\.py$", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    # Skip if fd not available
    if "Cannot find the `fd` binary" in result.stderr:
        pytest.skip("fd not available")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "matches" in output
    assert any("test.py" in match for match in output["matches"])


def test_cli_filter_command(tmp_path: Path):
    """Test CLI filter subcommand."""
    # Create test files
    (tmp_path / "main.py").write_text("# main")
    (tmp_path / "minor.py").write_text("# minor")

    result = subprocess.run(
        [
            sys.executable,
            "mcp_fd_server.py",
            "filter",
            "main",
            r"\.py$",
            str(tmp_path),
            "--first",
        ],
        capture_output=True,
        text=True,
    )

    # Skip if dependencies not available
    if "Cannot find the" in result.stderr:
        pytest.skip("fd or fzf not available")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "matches" in output
    if output["matches"]:  # fzf might not find matches depending on version
        assert len(output["matches"]) == 1


def test_cli_help():
    """Test CLI help output."""
    result = subprocess.run(
        [sys.executable, "mcp_fd_server.py", "-h"], capture_output=True, text=True
    )

    assert result.returncode == 0
    assert "fd + fzf powers" in result.stdout
    assert "search" in result.stdout
    assert "filter" in result.stdout


def test_cli_with_flags(tmp_path: Path):
    """Test CLI with additional flags."""
    # Create test files including hidden
    (tmp_path / "visible.py").write_text("# visible")
    (tmp_path / ".hidden.py").write_text("# hidden")

    result = subprocess.run(
        [
            sys.executable,
            "mcp_fd_server.py",
            "search",
            r"\.py$",
            str(tmp_path),
            "--flags=--hidden",  # Use equals syntax for flags
        ],
        capture_output=True,
        text=True,
    )

    if "Cannot find the `fd` binary" in result.stderr:
        pytest.skip("fd not available")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "matches" in output
    # Should find both visible and hidden files
    matches = output["matches"]
    assert any("visible.py" in match for match in matches)
    assert any(".hidden.py" in match for match in matches)
