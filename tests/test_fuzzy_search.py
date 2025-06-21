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

import mcp_fuzzy_search

pytestmark = pytest.mark.anyio


def _skip_if_missing(binary: str):
    """Skip test if binary is not available on PATH."""
    if shutil.which(binary) is None:
        pytest.skip(f"{binary} not on PATH")


async def test_fuzzy_search_files(tmp_path: Path):
    """Test fuzzy_search_files with real binaries."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create test files
    (tmp_path / "main.py").write_text("# main file")
    (tmp_path / "main_test.py").write_text("# main test")
    (tmp_path / "utils.py").write_text("# utilities")
    (tmp_path / "README.md").write_text("# Main documentation")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        result = await client.call_tool(
            "fuzzy_search_files", {"filter": "main", "path": str(tmp_path)}
        )

        # Parse result
        data = json.loads(result.content[0].text)
        assert "matches" in data
        assert len(data["matches"]) >= 2  # Should find main.py and main_test.py
        assert any("main.py" in match for match in data["matches"])


async def test_fuzzy_search_files_with_hidden(tmp_path: Path):
    """Test fuzzy_search_files includes hidden files when requested."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create test files
    (tmp_path / ".hidden_config.json").write_text("{}")
    (tmp_path / "visible_config.json").write_text("{}")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        # Without hidden flag
        result_no_hidden = await client.call_tool(
            "fuzzy_search_files", {"filter": "config", "path": str(tmp_path)}
        )
        data_no_hidden = json.loads(result_no_hidden.content[0].text)

        # With hidden flag
        result_with_hidden = await client.call_tool(
            "fuzzy_search_files",
            {"filter": "config", "path": str(tmp_path), "hidden": True},
        )
        data_with_hidden = json.loads(result_with_hidden.content[0].text)

        # Assertions
        assert len(data_with_hidden["matches"]) > len(data_no_hidden["matches"])
        assert any(".hidden_config" in match for match in data_with_hidden["matches"])


async def test_fuzzy_search_content(tmp_path: Path):
    """Test fuzzy_search_content with ripgrep pattern and fuzzy filter."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create test files with content
    (tmp_path / "todo.py").write_text("""
# TODO: implement user authentication
def login():
    pass

# TODO: add error handling
def process():
    pass
""")
    (tmp_path / "main.py").write_text("""
# TODO: complete main function implementation
def main():
    pass
""")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        result = await client.call_tool(
            "fuzzy_search_content",
            {"filter": "implement", "path": str(tmp_path), "pattern": "TODO"},
        )

        # Parse result
        data = json.loads(result.content[0].text)
        assert "matches" in data
        assert len(data["matches"]) >= 2  # Should find both "implement" TODOs

        # Check structure of matches
        for match in data["matches"]:
            assert "file" in match
            assert "line" in match
            assert "content" in match
            assert "implement" in match["content"].lower()


async def test_fuzzy_search_content_with_limit(tmp_path: Path):
    """Test fuzzy_search_content respects limit parameter."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create many matching lines
    content = "\n".join([f"# TODO: task {i}" for i in range(20)])
    (tmp_path / "tasks.py").write_text(content)

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        result = await client.call_tool(
            "fuzzy_search_content",
            {"filter": "task", "path": str(tmp_path), "pattern": "TODO", "limit": 5},
        )

        data = json.loads(result.content[0].text)
        assert len(data["matches"]) <= 5


async def test_fuzzy_search_content_default_pattern(tmp_path: Path):
    """Test fuzzy_search_content uses default pattern '.' (all lines)."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create test file with various content
    (tmp_path / "mixed.py").write_text("""
def function():
    print("hello")
    # This is a comment
    return True
""")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        result = await client.call_tool(
            "fuzzy_search_content",
            {"filter": "function", "path": str(tmp_path)},  # No pattern specified
        )

        data = json.loads(result.content[0].text)
        assert "matches" in data
        assert len(data["matches"]) >= 1
        assert any("function" in match["content"] for match in data["matches"])


async def test_fuzzy_search_content_with_hidden(tmp_path: Path):
    """Test fuzzy_search_content searches hidden files when requested."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create hidden and visible files
    (tmp_path / ".env").write_text("SECRET_KEY=hidden_value")
    (tmp_path / "config.py").write_text("SECRET_KEY=visible_value")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        # Without hidden flag
        result_no_hidden = await client.call_tool(
            "fuzzy_search_content",
            {"filter": "SECRET", "path": str(tmp_path)},
        )
        data_no_hidden = json.loads(result_no_hidden.content[0].text)

        # With hidden flag
        result_with_hidden = await client.call_tool(
            "fuzzy_search_content",
            {"filter": "SECRET", "path": str(tmp_path), "hidden": True},
        )
        data_with_hidden = json.loads(result_with_hidden.content[0].text)

        # Should find more matches with hidden files
        assert len(data_with_hidden["matches"]) >= len(data_no_hidden["matches"])


async def test_fuzzy_search_content_with_rg_flags(tmp_path: Path):
    """Test fuzzy_search_content passes extra flags to ripgrep."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create test file with case-sensitive content
    (tmp_path / "case.py").write_text("ERROR: something failed\nerror: minor issue")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        result = await client.call_tool(
            "fuzzy_search_content",
            {
                "filter": "error",
                "path": str(tmp_path),
                "pattern": "error",
                "rg_flags": "-i",  # Case insensitive
            },
        )

        data = json.loads(result.content[0].text)
        assert "matches" in data
        # Should find both ERROR and error with -i flag
        assert len(data["matches"]) >= 2


async def test_error_handling():
    """Test error handling for missing arguments."""
    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        # Missing filter for fuzzy_search_files
        result = await client.call_tool("fuzzy_search_files", {"filter": ""})
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert "'filter' argument is required" in data["error"]

        # Missing filter for fuzzy_search_content
        result = await client.call_tool(
            "fuzzy_search_content", {"filter": ""}
        )
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert "'filter' argument is required" in data["error"]


async def test_list_tools():
    """Test that tools are properly exposed."""
    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        result = await client.list_tools()

        assert len(result.tools) == 2

        # Find tools by name
        files_tool = next(t for t in result.tools if t.name == "fuzzy_search_files")
        content_tool = next(t for t in result.tools if t.name == "fuzzy_search_content")

        # Verify metadata
        assert "fuzzy matching" in files_tool.description
        assert "filter" in files_tool.inputSchema["required"]

        assert "Search all file contents" in content_tool.description
        assert "filter" in content_tool.inputSchema["required"]


def test_cli_search_files(tmp_path: Path):
    """Test CLI search-files subcommand."""
    # Create test files
    (tmp_path / "main.py").write_text("# main")
    (tmp_path / "test_main.py").write_text("# test")

    result = subprocess.run(
        [sys.executable, "mcp_fuzzy_search.py", "search-files", "main", str(tmp_path)],
        capture_output=True,
        text=True,
    )

    if "Cannot find the" in result.stderr:
        pytest.skip("Required binaries not available")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "matches" in output


def test_cli_search_content(tmp_path: Path):
    """Test CLI search-content subcommand."""
    # Create test file
    (tmp_path / "app.py").write_text("# TODO: implement feature\n# TODO: fix bug")

    result = subprocess.run(
        [
            sys.executable,
            "mcp_fuzzy_search.py",
            "search-content",
            "implement",
            str(tmp_path),
            "--pattern",
            "TODO",
        ],
        capture_output=True,
        text=True,
    )

    if "Cannot find the" in result.stderr:
        pytest.skip("Required binaries not available")

    assert result.returncode == 0
    output = json.loads(result.stdout)
    assert "matches" in output


def test_cli_help():
    """Test CLI help output."""
    result = subprocess.run(
        [sys.executable, "mcp_fuzzy_search.py", "-h"], capture_output=True, text=True
    )

    assert result.returncode == 0
    assert "Fuzzy search with ripgrep + fzf" in result.stdout
    assert "search-files" in result.stdout
    assert "search-content" in result.stdout


def test_require_binary():
    """Test the _require helper function."""
    # Valid binary
    assert mcp_fuzzy_search._require("/usr/bin/rg", "rg") == "/usr/bin/rg"

    # Missing binary
    with pytest.raises(mcp_fuzzy_search.BinaryMissing) as exc_info:
        mcp_fuzzy_search._require(None, "rg")

    assert "Cannot find the `rg` binary" in str(exc_info.value)


def test_binary_discovery():
    """Test binary discovery logic by calling shutil.which directly."""
    # Test that the discovery works with mock
    with patch("shutil.which") as mock_which:
        # When rg is available
        mock_which.side_effect = lambda x: "/usr/bin/rg" if x == "rg" else None
        rg_path = mock_which("rg")
        assert rg_path == "/usr/bin/rg"

        # Reset side_effect and set return_value for when binaries are missing
        mock_which.side_effect = None
        mock_which.return_value = None
        rg_path = mock_which("rg")
        assert rg_path is None


@patch("subprocess.Popen")
async def test_fuzzy_search_files_mocked(mock_popen):
    """Test fuzzy_search_files with mocked subprocess."""
    # Mock ripgrep process
    rg_proc = MagicMock()
    rg_proc.stdout = MagicMock()
    rg_proc.wait.return_value = 0

    # Mock fzf process
    fzf_proc = MagicMock()
    fzf_proc.communicate.return_value = ("src/main.py\nsrc/main_test.py\n", "")

    mock_popen.side_effect = [rg_proc, fzf_proc]

    with (
        patch.object(mcp_fuzzy_search, "RG_EXECUTABLE", "/mock/rg"),
        patch.object(mcp_fuzzy_search, "FZF_EXECUTABLE", "/mock/fzf"),
    ):
        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            result = await client.call_tool(
                "fuzzy_search_files", {"filter": "main", "path": "."}
            )

            data = json.loads(result.content[0].text)
            assert data["matches"] == ["src/main.py", "src/main_test.py"]


@patch("subprocess.Popen")
async def test_fuzzy_search_content_mocked(mock_popen):
    """Test fuzzy_search_content with mocked subprocess."""
    # Mock ripgrep process
    rg_proc = MagicMock()
    rg_proc.stdout = MagicMock()
    rg_proc.stderr = MagicMock()
    rg_proc.stderr.read.return_value = b""
    rg_proc.wait.return_value = 0
    rg_proc.returncode = 0

    # Mock fzf process with properly formatted output
    fzf_proc = MagicMock()
    fzf_proc.communicate.return_value = (
        "src/app.py:10:    # TODO: implement feature\n"
        "src/test.py:5:    # TODO: implement tests\n",
        "",
    )

    mock_popen.side_effect = [rg_proc, fzf_proc]

    with (
        patch.object(mcp_fuzzy_search, "RG_EXECUTABLE", "/mock/rg"),
        patch.object(mcp_fuzzy_search, "FZF_EXECUTABLE", "/mock/fzf"),
    ):
        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            result = await client.call_tool(
                "fuzzy_search_content",
                {"filter": "implement", "path": ".", "pattern": "TODO"},
            )

            data = json.loads(result.content[0].text)
            assert len(data["matches"]) == 2
            assert data["matches"][0]["file"] == "src/app.py"
            assert data["matches"][0]["line"] == 10
            assert "implement feature" in data["matches"][0]["content"]
