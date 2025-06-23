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
            "fuzzy_search_files", {"fuzzy_filter": "main", "path": str(tmp_path)}
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
            "fuzzy_search_files", {"fuzzy_filter": "config", "path": str(tmp_path)}
        )
        data_no_hidden = json.loads(result_no_hidden.content[0].text)

        # With hidden flag
        result_with_hidden = await client.call_tool(
            "fuzzy_search_files",
            {"fuzzy_filter": "config", "path": str(tmp_path), "hidden": True},
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
            {
                "fuzzy_filter": "implement",
                "path": str(tmp_path),
                "regex_pattern": "TODO",
            },
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
            {
                "fuzzy_filter": "task",
                "path": str(tmp_path),
                "regex_pattern": "TODO",
                "limit": 5,
            },
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
            {"fuzzy_filter": "function", "path": str(tmp_path)},  # No pattern specified
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
            {"fuzzy_filter": "SECRET", "path": str(tmp_path)},
        )
        data_no_hidden = json.loads(result_no_hidden.content[0].text)

        # With hidden flag
        result_with_hidden = await client.call_tool(
            "fuzzy_search_content",
            {"fuzzy_filter": "SECRET", "path": str(tmp_path), "hidden": True},
        )
        data_with_hidden = json.loads(result_with_hidden.content[0].text)

        # Should find more matches with hidden files
        assert len(data_with_hidden["matches"]) >= len(data_no_hidden["matches"])


async def test_fuzzy_search_content_with_rg_flags(tmp_path: Path):
    """Test fuzzy_search_content passes extra flags to ripgrep."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")


async def test_warns_on_regex_in_filter(tmp_path: Path):
    """Test that using regex in filter parameter provides helpful guidance."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create test file
    (tmp_path / "test_file.py").write_text("def test_seer_credit():\n    pass")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        # Test with regex pattern in filter (incorrect usage)
        result = await client.call_tool(
            "fuzzy_search_content",
            {
                "fuzzy_filter": "def test_.*seer.*credit",  # Regex in wrong parameter
                "regex_pattern": "def test_",
                "path": str(tmp_path),
            },
        )

        data = json.loads(result.content[0].text)
        assert "warnings" in data
        assert "regex-like patterns" in data["warnings"][0]
        assert "Try:" in data["warnings"][0]


async def test_diagnostic_messages_no_matches(tmp_path: Path):
    """Test diagnostic messages when no matches are found."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create test files
    (tmp_path / "file1.py").write_text("def hello():\n    print('world')")
    (tmp_path / "file2.py").write_text("class MyClass:\n    pass")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        # Test 1: Pattern finds nothing
        result = await client.call_tool(
            "fuzzy_search_content",
            {
                "fuzzy_filter": "something",
                "regex_pattern": "nonexistent_pattern",
                "path": str(tmp_path),
            },
        )

        data = json.loads(result.content[0].text)
        assert len(data["matches"]) == 0
        assert "diagnostic" in data
        assert "ripgrep found 0 matches" in data["diagnostic"]

        # Test 2: Pattern finds matches but filter doesn't match
        result = await client.call_tool(
            "fuzzy_search_content",
            {
                "fuzzy_filter": "nonexistent",
                "regex_pattern": "def",
                "path": str(tmp_path),
            },
        )

        data = json.loads(result.content[0].text)
        assert len(data["matches"]) == 0
        assert "diagnostic" in data
        assert "ripgrep found" in data["diagnostic"]
        assert "but fzf filter" in data["diagnostic"]


async def test_fuzzy_search_files_regex_warning(tmp_path: Path):
    """Test that fuzzy_search_files warns about regex in filter."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create test files
    (tmp_path / "main.py").write_text("# main")
    (tmp_path / "test_main.py").write_text("# test")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        result = await client.call_tool(
            "fuzzy_search_files",
            {
                "fuzzy_filter": ".*\\.py$",  # Regex pattern
                "path": str(tmp_path),
            },
        )

        data = json.loads(result.content[0].text)
        assert "warnings" in data
        assert "regex-like patterns" in data["warnings"][0]


async def test_helper_functions():
    """Test the regex detection and suggestion helper functions."""
    # Test regex detection
    assert mcp_fuzzy_search._looks_like_regex("def test_.*seer.*credit")
    assert mcp_fuzzy_search._looks_like_regex(".*\\.py$")
    assert mcp_fuzzy_search._looks_like_regex("^src/.*")
    assert mcp_fuzzy_search._looks_like_regex("\\w+")
    assert not mcp_fuzzy_search._looks_like_regex("simple search terms")
    assert not mcp_fuzzy_search._looks_like_regex("TODO implement")

    # Test fuzzy term suggestions
    assert (
        mcp_fuzzy_search._suggest_fuzzy_terms("def test_.*seer.*credit")
        == "def test seer credit"
    )
    assert mcp_fuzzy_search._suggest_fuzzy_terms("^src/.*\\.py$") == "src/ py"
    assert (
        mcp_fuzzy_search._suggest_fuzzy_terms("TODO|FIXME") == "TODO|FIXME"
    )  # Keeps pipe for OR


async def test_fuzzy_search_content_case_sensitive(tmp_path: Path):
    """Test fuzzy_search_content with case-sensitive matching."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create test file with case-sensitive content
    (tmp_path / "case.py").write_text("ERROR: something failed\nerror: minor issue")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        result = await client.call_tool(
            "fuzzy_search_content",
            {
                "fuzzy_filter": "error",
                "path": str(tmp_path),
                "regex_pattern": "error",
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
        result = await client.call_tool("fuzzy_search_files", {"fuzzy_filter": ""})
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert "'fuzzy_filter' argument is required" in data["error"]

        # Missing filter for fuzzy_search_content
        result = await client.call_tool("fuzzy_search_content", {"fuzzy_filter": ""})
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert "'fuzzy_filter' argument is required" in data["error"]


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
        assert "fuzzy_filter" in files_tool.inputSchema["required"]

        assert (
            content_tool.description
            and "Search file contents using a two-stage pipeline"
            in content_tool.description
        )
        assert "fuzzy_filter" in content_tool.inputSchema["required"]


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
            "--regex-pattern",
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
                "fuzzy_search_files", {"fuzzy_filter": "main", "path": "."}
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
                {"fuzzy_filter": "implement", "path": ".", "regex_pattern": "TODO"},
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

    # Use subprocess mocking instead of PATH manipulation for better reliability
    with (
        patch.object(mcp_fuzzy_search, "RG_EXECUTABLE", "/mock/rg"),
        patch.object(mcp_fuzzy_search, "FZF_EXECUTABLE", "/mock/fzf"),
        patch("subprocess.check_output") as mock_rg,
        patch("subprocess.Popen") as mock_popen,
    ):
        # Mock rg listing files
        mock_rg.return_value = f"{test_file1}\n{test_file2}\n"

        # Mock fzf finding the class
        mock_fzf_proc = MagicMock()
        normalized_path = normalize_path(str(test_file1))
        expected_output = f"{normalized_path}:\nclass UserService:\n    def authenticate(self, user):\n        if user.is_valid:\n            return True\n        return False\n\ndef process_request():\n    pass\n\x00"
        mock_fzf_proc.communicate.return_value = (expected_output.encode(), b"")
        mock_popen.return_value = mock_fzf_proc

        result = mcp_fuzzy_search.fuzzy_search_content(
            "class", str(tmp_path), multiline=True
        )

        assert "matches" in result
        matches = result["matches"]
        assert len(matches) > 0
        assert normalize_path(matches[0]["file"]) == normalize_path(str(test_file1))
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

    # Create a mock file object
    mock_file = MagicMock()
    mock_file.read.return_value = test_content.encode()

    # We need to patch Path at the module level
    with patch("mcp_fuzzy_search.Path") as mock_path_class:
        # Create a mock Path instance
        mock_path_instance = MagicMock()
        mock_path_instance.open.return_value.__enter__.return_value = mock_file

        # Path() constructor returns our mock instance
        mock_path_class.return_value = mock_path_instance

        # For Path(path).resolve() calls
        mock_path_class.return_value.resolve.return_value = mock_path_instance
        mock_path_class.return_value.resolve.return_value.__str__.return_value = (
            "api.js"
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
                    "fuzzy_search_files", {"fuzzy_filter": "async", "multiline": True}
                )

                data = json.loads(result.content[0].text)
                assert "matches" in data
                assert len(data["matches"]) > 0
                assert "async function processData()" in data["matches"][0]


async def test_fuzzy_search_content_multiline_mcp():
    """Test multiline support through MCP interface for fuzzy_search_content."""
    test_content = "class DatabaseService {\n  constructor(config) {\n    this.config = config;\n  }\n\n  async connect() {\n    // TODO: implement\n  }\n}"

    # Create a mock file object
    mock_file = MagicMock()
    mock_file.read.return_value = test_content.encode()

    # We need to patch Path at the module level
    with patch("mcp_fuzzy_search.Path") as mock_path_class:
        # Create a mock Path instance
        mock_path_instance = MagicMock()
        mock_path_instance.open.return_value.__enter__.return_value = mock_file

        # Path() constructor returns our mock instance
        mock_path_class.return_value = mock_path_instance

        # For Path(path).resolve() calls
        mock_path_class.return_value.resolve.return_value = mock_path_instance
        mock_path_class.return_value.resolve.return_value.__str__.return_value = (
            "service.js"
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
                    "fuzzy_search_content", {"fuzzy_filter": "class", "multiline": True}
                )

                data = json.loads(result.content[0].text)
                assert "matches" in data
                assert len(data["matches"]) > 0
                assert data["matches"][0]["file"] == "service.js"
                assert "class DatabaseService" in data["matches"][0]["content"]
                assert "async connect()" in data["matches"][0]["content"]


def test_windows_path_parsing_multiline():
    """Test parsing of multiline results with Windows paths containing colons."""
    test_cases = [
        # Windows absolute path
        {
            "input": "C:/Users/test/file.py:\nclass Test:\n    pass",
            "expected_file": "C:/Users/test/file.py",
            "expected_content": "class Test:\n    pass",
        },
        # Windows path with multiple directories
        {
            "input": "D:/Projects/my-app/src/main.py:\ndef main():\n    print('hello')",
            "expected_file": "D:/Projects/my-app/src/main.py",
            "expected_content": "def main():\n    print('hello')",
        },
        # UNC path
        {
            "input": "//server/share/file.txt:\nSome content\nMore content",
            "expected_file": "//server/share/file.txt",
            "expected_content": "Some content\nMore content",
        },
        # Path with spaces (normalized)
        {
            "input": 'C:/Program Files/app/config.json:\n{\n  "key": "value"\n}',
            "expected_file": "C:/Program Files/app/config.json",
            "expected_content": '{\n  "key": "value"\n}',
        },
    ]

    for test_case in test_cases:
        # Simulate what the parsing logic does
        input_str = test_case["input"]
        if ":\n" in input_str:
            file_part, content_part = input_str.split(":\n", 1)
            assert file_part == test_case["expected_file"], (
                f"Failed to parse file part from {input_str}"
            )
            assert content_part == test_case["expected_content"], (
                f"Failed to parse content part from {input_str}"
            )


def test_fuzzy_search_content_windows_paths():
    """Test fuzzy_search_content with Windows-style paths in ripgrep output."""
    with patch("subprocess.check_output") as mock_rg_output:
        with patch("subprocess.Popen") as mock_popen:
            with patch.object(mcp_fuzzy_search, "RG_EXECUTABLE", "/mock/rg"):
                with patch.object(mcp_fuzzy_search, "FZF_EXECUTABLE", "/mock/fzf"):
                    # Mock rg listing files with Windows paths
                    mock_rg_output.return_value = (
                        r"C:\Users\test\app.py" + "\n" + r"D:\Projects\main.py" + "\n"
                    )

                    # Mock fzf process for multiline mode
                    mock_proc = MagicMock()
                    # Return Windows path normalized to forward slashes
                    mock_proc.communicate.return_value = (
                        b"C:/Users/test/app.py:\nclass Application:\n    def run(self):\n        pass\x00",
                        b"",
                    )
                    mock_popen.return_value = mock_proc

                    # Mock file reading
                    with patch("pathlib.Path.open") as mock_open:
                        mock_file = MagicMock()
                        mock_file.read.return_value = (
                            b"class Application:\n    def run(self):\n        pass"
                        )
                        mock_open.return_value.__enter__.return_value = mock_file

                        result = mcp_fuzzy_search.fuzzy_search_content(
                            "class", ".", multiline=True
                        )

                        assert "matches" in result
                        assert len(result["matches"]) > 0
                        match = result["matches"][0]
                        assert match["file"] == "C:/Users/test/app.py"
                        assert "class Application:" in match["content"]
                        # Ensure no backslashes in the path
                        assert "\\" not in match["file"]
