import json
import os
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


def normalize_path(path):
    """Normalize path to use forward slashes for cross-platform testing."""
    # Use pathlib for proper path handling
    return Path(path).as_posix()


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
        result = await client.call_tool("fuzzy_search_content", {"filter": ""})
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
        assert files_tool.description and "fuzzy matching" in files_tool.description
        assert "filter" in files_tool.inputSchema["required"]

        assert (
            content_tool.description
            and "Search all file contents" in content_tool.description
        )
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


# Multiline support tests

monkeypatch = pytest.MonkeyPatch()


def test_fuzzy_search_files_multiline(tmp_path: Path):
    """Test multiline support in fuzzy_search_files."""
    # Create test files with content
    test_file1 = tmp_path / "code.js"
    test_file1.write_text(
        "function example() {\n  return 'hello';\n}\n\nclass TestClass {\n  constructor() {}\n}"
    )

    test_file2 = tmp_path / "data.py"
    test_file2.write_text("def process():\n    print('processing')")

    mock_rg = tmp_path / "rg"
    mock_rg.write_text(f'''#!/usr/bin/env python3
import sys
if "--files" in sys.argv:
    print("{test_file1}")
    print("{test_file2}")
''')
    mock_rg.chmod(0o755)

    mock_fzf = tmp_path / "fzf"
    mock_fzf.write_text(f'''#!/usr/bin/env python3
import sys
if "--read0" in sys.argv and "--print0" in sys.argv:
    # Read null-delimited input
    data = sys.stdin.buffer.read()
    # Look for "function" in the content
    if b"function" in data:
        # Return matching file record with null terminator
        content = "{test_file1}:\\nfunction example() {{\\n  return 'hello';\\n}}\\n\\nclass TestClass {{\\n  constructor() {{}}\\n}}"
        print(content, end="\\0")
''')
    mock_fzf.chmod(0o755)

    with monkeypatch.context() as m:
        m.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")

        # Reload module globals to pick up new executables
        mcp_fuzzy_search.RG_EXECUTABLE = shutil.which("rg")
        mcp_fuzzy_search.FZF_EXECUTABLE = shutil.which("fzf")

        result = mcp_fuzzy_search.fuzzy_search_files(
            "function", str(tmp_path), multiline=True
        )

        assert "matches" in result
        matches = result["matches"]
        assert len(matches) > 0
        assert "function example()" in matches[0]
        assert "class TestClass" in matches[0]


def test_fuzzy_search_content_multiline(tmp_path: Path):
    """Test multiline support in fuzzy_search_content."""
    # Create test files with multi-line patterns
    test_file1 = tmp_path / "service.py"
    test_file1.write_text("""
class UserService:
    def authenticate(self, user):
        if user.is_valid:
            return True
        return False

def process_request():
    pass
""")

    test_file2 = tmp_path / "model.py"
    test_file2.write_text(
        "class User:\n    def __init__(self):\n        self.name = ''\n        self.email = ''"
    )

    mock_rg = tmp_path / "rg"
    mock_rg.write_text(f'''#!/usr/bin/env python3
import sys
if "--files" in sys.argv:
    print("{test_file1}")
    print("{test_file2}")
''')
    mock_rg.chmod(0o755)

    mock_fzf = tmp_path / "fzf"
    mock_fzf.write_text(f'''#!/usr/bin/env python3
import sys
if "--read0" in sys.argv and "--print0" in sys.argv:
    # Read null-delimited input
    data = sys.stdin.buffer.read()
    # Look for "class.*:" pattern in the content
    if b"class" in data:
        # Return matching file record with null terminator
        content = "{test_file1}:\\nclass UserService:\\n    def authenticate(self, user):\\n        if user.is_valid:\\n            return True\\n        return False"
        print(content, end="\\0")
''')
    mock_fzf.chmod(0o755)

    with monkeypatch.context() as m:
        m.setenv("PATH", f"{tmp_path}:{os.environ.get('PATH', '')}")

        # Reload module globals to pick up new executables
        mcp_fuzzy_search.RG_EXECUTABLE = shutil.which("rg")
        mcp_fuzzy_search.FZF_EXECUTABLE = shutil.which("fzf")

        result = mcp_fuzzy_search.fuzzy_search_content(
            "class", str(tmp_path), multiline=True
        )

        assert "matches" in result
        matches = result["matches"]
        assert len(matches) > 0
        assert matches[0]["file"] == str(test_file1)
        assert "class UserService:" in matches[0]["content"]
        assert "def authenticate" in matches[0]["content"]


def test_multiline_cli_support():
    """Test CLI support for multiline flags."""
    # Test search-files multiline
    with patch("mcp_fuzzy_search.fuzzy_search_files") as mock_search_files:
        mock_search_files.return_value = {"matches": ["file1.txt"]}

        with patch(
            "sys.argv",
            ["mcp_fuzzy_search.py", "search-files", "test", ".", "--multiline"],
        ):
            mcp_fuzzy_search._cli()

        # Verify multiline=True was passed - check both positional and keyword args
        mock_search_files.assert_called_once()
        call_args = mock_search_files.call_args
        # Function signature: fuzzy_search_files(filter, path, hidden, limit, multiline)
        if len(call_args[0]) > 4:
            assert call_args[0][4] is True  # positional argument
        else:
            assert call_args[1].get("multiline") is True

    # Test search-content multiline
    with patch("mcp_fuzzy_search.fuzzy_search_content") as mock_search_content:
        mock_search_content.return_value = {"matches": []}

        with patch(
            "sys.argv",
            ["mcp_fuzzy_search.py", "search-content", "test", ".", "--multiline"],
        ):
            mcp_fuzzy_search._cli()

        # Verify multiline=True was passed
        mock_search_content.assert_called_once()
        call_args = mock_search_content.call_args
        # Function signature: fuzzy_search_content(filter, path, pattern, hidden, limit, rg_flags, multiline)
        if len(call_args[0]) > 6:
            assert call_args[0][6] is True  # positional argument
        else:
            assert call_args[1].get("multiline") is True


async def test_fuzzy_search_files_multiline_mcp():
    """Test multiline support through MCP interface for fuzzy_search_files."""
    test_content = "async function processData() {\n  const result = await fetch('/api');\n  return result.json();\n}"

    with patch("builtins.open", create=True) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = (
            test_content.encode()
        )

        with (
            patch.object(mcp_fuzzy_search, "RG_EXECUTABLE", "/mock/rg"),
            patch.object(mcp_fuzzy_search, "FZF_EXECUTABLE", "/mock/fzf"),
            patch("subprocess.check_output") as mock_rg_output,
            patch("subprocess.Popen") as mock_popen,
        ):
            # Mock rg listing files
            mock_rg_output.return_value = "api.js\n"

            # Mock fzf finding the async function
            mock_fzf_proc = MagicMock()
            mock_fzf_proc.communicate.return_value = (
                b"api.js:\nasync function processData() {\n  const result = await fetch('/api');\n  return result.json();\n}\x00",
                b"",
            )
            mock_popen.return_value = mock_fzf_proc

            async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
                result = await client.call_tool(
                    "fuzzy_search_files", {"filter": "async", "multiline": True}
                )

                data = json.loads(result.content[0].text)
                assert "matches" in data
                assert len(data["matches"]) > 0
                assert "async function processData()" in data["matches"][0]


async def test_fuzzy_search_content_multiline_mcp():
    """Test multiline support through MCP interface for fuzzy_search_content."""
    test_content = "class DatabaseService {\n  constructor(config) {\n    this.config = config;\n  }\n\n  async connect() {\n    // TODO: implement\n  }\n}"

    with patch("builtins.open", create=True) as mock_open:
        mock_open.return_value.__enter__.return_value.read.return_value = (
            test_content.encode()
        )

        with (
            patch.object(mcp_fuzzy_search, "RG_EXECUTABLE", "/mock/rg"),
            patch.object(mcp_fuzzy_search, "FZF_EXECUTABLE", "/mock/fzf"),
            patch("subprocess.check_output") as mock_rg_output,
            patch("subprocess.Popen") as mock_popen,
        ):
            # Mock rg listing files
            mock_rg_output.return_value = "service.js\n"

            # Mock fzf finding the class
            mock_fzf_proc = MagicMock()
            mock_fzf_proc.communicate.return_value = (
                b"service.js:\nclass DatabaseService {\n  constructor(config) {\n    this.config = config;\n  }\n\n  async connect() {\n    // TODO: implement\n  }\n}\x00",
                b"",
            )
            mock_popen.return_value = mock_fzf_proc

            async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
                result = await client.call_tool(
                    "fuzzy_search_content", {"filter": "class", "multiline": True}
                )

                data = json.loads(result.content[0].text)
                assert "matches" in data
                assert len(data["matches"]) > 0
                assert data["matches"][0]["file"] == "service.js"
                assert "class DatabaseService" in data["matches"][0]["content"]
                assert "async connect()" in data["matches"][0]["content"]
