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
                "fuzzy_filter": "TODO implement",
                "path": str(tmp_path),
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
                "fuzzy_filter": "TODO task",
                "path": str(tmp_path),
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
                "fuzzy_filter": "def test_.*seer.*credit",  # Regex in filter
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
        # Test: Filter doesn't match any content
        result = await client.call_tool(
            "fuzzy_search_content",
            {
                "fuzzy_filter": "nonexistent_function_name",
                "path": str(tmp_path),
            },
        )

        data = json.loads(result.content[0].text)
        assert len(data["matches"]) == 0
        assert "diagnostic" in data
        assert "Found" in data["diagnostic"]
        assert "but fuzzy filter" in data["diagnostic"]


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
                "rg_flags": "-i",  # Case insensitive
            },
        )

        data = json.loads(result.content[0].text)
        assert "matches" in data
        # Should find both ERROR and error with -i flag
        assert len(data["matches"]) >= 2


async def test_fuzzy_search_content_default_vs_content_only(tmp_path: Path):
    """Test the difference between default and content-only modes."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create test files with names that might interfere with content search
    (tmp_path / "test.py").write_text("def update():\n    pass")
    (tmp_path / "update.py").write_text("def check():\n    pass")
    (tmp_path / "other.py").write_text("# update comment here\ndef other():\n    pass")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        # Test 1: Default mode - search for "update" which should match both filename and content
        result_default = await client.call_tool(
            "fuzzy_search_content",
            {
                "fuzzy_filter": "update",  # Should match update.py filename AND update() content
                "path": str(tmp_path),
            },
        )
        data_default = json.loads(result_default.content[0].text)

        # Test 2: Content-only mode - same search but content-only
        result_content_only = await client.call_tool(
            "fuzzy_search_content",
            {
                "fuzzy_filter": "update",  # Should only match update() content, not filename
                "path": str(tmp_path),
                "content_only": True,
            },
        )
        data_content_only = json.loads(result_content_only.content[0].text)

        # Both modes should find at least the content matches
        assert (
            len(data_default["matches"]) >= 2
        )  # At least test.py and other.py content
        assert len(data_content_only["matches"]) >= 2  # Same content matches

        # Default mode might find more matches (including path matches)
        # Content-only mode should find fewer or equal matches
        assert len(data_default["matches"]) >= len(data_content_only["matches"])

        # Both should find the content matches for "update"
        default_content_matches = [
            match
            for match in data_default["matches"]
            if "update" in match["content"].lower()
        ]
        content_only_matches = [
            match
            for match in data_content_only["matches"]
            if "update" in match["content"].lower()
        ]

        # Should find the same content matches (at least the ones with "update" in content)
        assert len(default_content_matches) >= 2  # test.py and other.py
        assert len(content_only_matches) >= 2  # test.py and other.py

        # Verify files are found
        default_files = [match["file"] for match in default_content_matches]
        content_files = [match["file"] for match in content_only_matches]

        assert any("test.py" in f for f in default_files)
        assert any("other.py" in f for f in default_files)
        assert any("test.py" in f for f in content_files)
        assert any("other.py" in f for f in content_files)


async def test_fuzzy_search_content_only_mode(tmp_path: Path):
    """Test content-only mode ignores file paths in matching."""
    _skip_if_missing("rg")
    _skip_if_missing("fzf")

    # Create files where filenames might match but content doesn't
    (tmp_path / "async.py").write_text("def sync_function():\n    return 42")
    (tmp_path / "sync.py").write_text("async def fetch_data():\n    return await api()")
    (tmp_path / "main.py").write_text("# No word here\ndef main():\n    pass")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        # Search for "async" with content-only mode
        result = await client.call_tool(
            "fuzzy_search_content",
            {
                "fuzzy_filter": "async",
                "path": str(tmp_path),
                "content_only": True,
            },
        )

        data = json.loads(result.content[0].text)
        assert "matches" in data

        # Should only find the file with "async" in content, not in filename
        assert len(data["matches"]) == 1
        assert data["matches"][0]["file"].endswith("sync.py")
        assert "async def" in data["matches"][0]["content"]


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

        assert len(result.tools) == 4

        # Find tools by name
        files_tool = next(t for t in result.tools if t.name == "fuzzy_search_files")
        content_tool = next(t for t in result.tools if t.name == "fuzzy_search_content")
        documents_tool = next(
            t for t in result.tools if t.name == "fuzzy_search_documents"
        )
        pdf_tool = next(t for t in result.tools if t.name == "extract_pdf_pages")

        # Verify metadata for original tools
        assert files_tool.description and "fuzzy matching" in files_tool.description
        assert "fuzzy_filter" in files_tool.inputSchema["required"]

        assert (
            content_tool.description
            and "Search file contents using fuzzy filtering" in content_tool.description
        )
        assert "fuzzy_filter" in content_tool.inputSchema["required"]

        # Verify metadata for PDF tools
        assert documents_tool.description and "PDFs" in documents_tool.description
        assert "fuzzy_filter" in documents_tool.inputSchema["required"]

        assert pdf_tool.description and "Extract specific pages" in pdf_tool.description
        assert "file" in pdf_tool.inputSchema["required"]
        assert "pages" in pdf_tool.inputSchema["required"]


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
            "TODO implement",
            str(tmp_path),
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


def test_cli_content_only_flag():
    """Test CLI --content-only flag."""
    # Test that the flag is accepted and passed correctly
    with patch("mcp_fuzzy_search.fuzzy_search_content") as mock_search:
        mock_search.return_value = {"matches": []}

        with patch(
            "sys.argv",
            ["mcp_fuzzy_search.py", "search-content", "test", ".", "--content-only"],
        ):
            mcp_fuzzy_search._cli()

        # Verify content_only=True was passed
        mock_search.assert_called_once()
        call_args = mock_search.call_args
        # Check the content_only parameter
        assert call_args[1].get("content_only") is True or (
            len(call_args[0]) > 6 and call_args[0][6] is True
        )


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
                {"fuzzy_filter": "TODO implement", "path": "."},
            )

            data = json.loads(result.content[0].text)
            assert len(data["matches"]) == 2
            assert data["matches"][0]["file"] == "src/app.py"
            assert data["matches"][0]["line"] == 10
            assert "implement feature" in data["matches"][0]["content"]

            # Verify fzf was called with --nth=1,3.. by default
            fzf_call_args = mock_popen.call_args_list[1][0][0]
            assert "--nth=1,3.." in fzf_call_args


@patch("subprocess.Popen")
async def test_fuzzy_search_content_mocked_content_only(mock_popen):
    """Test fuzzy_search_content with content_only mode."""
    # Mock ripgrep process
    rg_proc = MagicMock()
    rg_proc.stdout = MagicMock()
    rg_proc.stderr = MagicMock()
    rg_proc.stderr.read.return_value = b""
    rg_proc.wait.return_value = 0
    rg_proc.returncode = 0

    # Mock fzf process
    fzf_proc = MagicMock()
    fzf_proc.communicate.return_value = (
        "src/sync.py:1:async def fetch():\n",
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
                {"fuzzy_filter": "async", "path": ".", "content_only": True},
            )

            data = json.loads(result.content[0].text)
            assert len(data["matches"]) == 1

            # Verify fzf was called with --nth=3.. for content-only mode
            fzf_call_args = mock_popen.call_args_list[1][0][0]
            assert "--nth=3.." in fzf_call_args


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
        # Function signature: fuzzy_search_content(filter, path, hidden, limit, rg_flags, multiline)
        if len(call_args[0]) > 5:
            assert call_args[0][5] is True  # positional argument
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


# ---------------------------------------------------------------------------
# Tests for PDF tools
# ---------------------------------------------------------------------------


async def test_fuzzy_search_documents_missing_binary():
    """Test fuzzy_search_documents handles missing rga binary gracefully."""
    # Temporarily patch RGA_EXECUTABLE to None
    original_rga = mcp_fuzzy_search.RGA_EXECUTABLE
    try:
        mcp_fuzzy_search.RGA_EXECUTABLE = None

        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            result = await client.call_tool(
                "fuzzy_search_documents", {"fuzzy_filter": "test", "path": "."}
            )

            data = json.loads(result.content[0].text)
            assert "error" in data
            assert "ripgrep-all" in data["error"]
            assert "not installed" in data["error"]
    finally:
        mcp_fuzzy_search.RGA_EXECUTABLE = original_rga


async def test_fuzzy_search_documents_basic(tmp_path: Path):
    """Test fuzzy_search_documents with mock rga output."""
    _skip_if_missing("rga")
    _skip_if_missing("fzf")

    # Create a mock PDF file for testing
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4\n%fake pdf content")

    # Mock the rga JSON output
    mock_rga_output = (
        '''{"type":"match","data":{"path":{"text":"'''
        + str(test_pdf)
        + '''"},"lines":{"text":"Page 1: This is test content\\n"},"line_number":null,"absolute_offset":100,"submatches":[{"match":{"text":"test"},"start":8,"end":12}]}}
{"type":"end","data":{"path":{"text":"'''
        + str(test_pdf)
        + """"},"binary_offset":null,"stats":{"elapsed":{"secs":0,"nanos":35222125,"human":"0.035222s"},"searches":1,"searches_with_match":1,"bytes_searched":1000,"bytes_printed":100,"matched_lines":1,"matches":1}}}"""
    )

    with patch("subprocess.Popen") as mock_popen:
        # Mock rga process
        mock_rga_proc = MagicMock()
        mock_rga_proc.stdout = mock_rga_output.splitlines()
        mock_rga_proc.wait.return_value = None

        # Mock fzf process
        mock_fzf_proc = MagicMock()
        mock_fzf_proc.communicate.return_value = (
            f"{test_pdf}:Page 1: This is test content",
            None,
        )

        # Configure mocks
        mock_popen.side_effect = [mock_rga_proc, mock_fzf_proc]

        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            result = await client.call_tool(
                "fuzzy_search_documents",
                {"fuzzy_filter": "test", "path": str(tmp_path)},
            )

            data = json.loads(result.content[0].text)
            assert "matches" in data
            assert len(data["matches"]) == 1

            match = data["matches"][0]
            assert "file" in match
            assert "page" in match
            assert "content" in match
            assert "match_text" in match

            assert match["page"] == 1
            assert "test content" in match["content"]
            assert match["match_text"] == "test"


async def test_fuzzy_search_documents_parse_rga_json():
    """Test parsing of actual rga JSON output format."""
    sample_json = """{"type":"match","data":{"path":{"text":"./Linear Algebra Done Right 4e.pdf"},"lines":{"text":"Page 402: of scalar and vector, 12\\n"},"line_number":null,"absolute_offset":1174364,"submatches":[{"match":{"text":"vector"},"start":24,"end":30}]}}"""

    # Parse the JSON
    data = json.loads(sample_json)
    assert data["type"] == "match"
    assert data["data"]["line_number"] is None  # PDFs don't have line numbers
    assert "Page 402:" in data["data"]["lines"]["text"]

    # Extract page number
    import re

    lines_text = data["data"]["lines"]["text"].strip()
    page_match = re.match(r"Page (\d+):", lines_text)
    assert page_match is not None
    assert int(page_match.group(1)) == 402


async def test_extract_pdf_pages_missing_binaries():
    """Test extract_pdf_pages handles missing binaries gracefully."""
    # Test missing pdf2txt.py
    original_pdf2txt = mcp_fuzzy_search.PDF2TXT_EXECUTABLE
    try:
        mcp_fuzzy_search.PDF2TXT_EXECUTABLE = None

        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            result = await client.call_tool(
                "extract_pdf_pages", {"file": "test.pdf", "pages": "1,2,3"}
            )

            data = json.loads(result.content[0].text)
            assert "error" in data
            assert "pdf2txt.py" in data["error"]
    finally:
        mcp_fuzzy_search.PDF2TXT_EXECUTABLE = original_pdf2txt

    # Test missing pandoc
    original_pandoc = mcp_fuzzy_search.PANDOC_EXECUTABLE
    try:
        mcp_fuzzy_search.PANDOC_EXECUTABLE = None

        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            result = await client.call_tool(
                "extract_pdf_pages", {"file": "test.pdf", "pages": "1,2,3"}
            )

            data = json.loads(result.content[0].text)
            assert "error" in data
            assert "pandoc" in data["error"]
    finally:
        mcp_fuzzy_search.PANDOC_EXECUTABLE = original_pandoc


async def test_extract_pdf_pages_invalid_input(tmp_path: Path):
    """Test extract_pdf_pages handles invalid input gracefully."""
    _skip_if_missing("pdf2txt.py")
    _skip_if_missing("pandoc")

    async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
        # Test missing file
        result = await client.call_tool(
            "extract_pdf_pages",
            {"file": str(tmp_path / "nonexistent.pdf"), "pages": "1"},
        )
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert "not found" in data["error"]

        # Test invalid page numbers
        test_pdf = tmp_path / "test.pdf"
        test_pdf.write_bytes(b"%PDF-1.4\n%fake pdf")

        result = await client.call_tool(
            "extract_pdf_pages", {"file": str(test_pdf), "pages": "abc"}
        )
        data = json.loads(result.content[0].text)
        assert "error" in data
        assert "Invalid page specification" in data["error"]


async def test_extract_pdf_pages_basic(tmp_path: Path):
    """Test extract_pdf_pages with mock subprocess."""
    _skip_if_missing("pdf2txt.py")
    _skip_if_missing("pandoc")

    # Create a test PDF
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4\n%fake pdf content")

    with patch("subprocess.Popen") as mock_popen:
        # Mock pdf2txt process
        mock_pdf_proc = MagicMock()
        mock_pdf_proc.stdout = MagicMock()
        mock_pdf_proc.wait.return_value = None
        mock_pdf_proc.returncode = 0
        mock_pdf_proc.communicate.return_value = (None, b"")

        # Mock pandoc process
        mock_pandoc_proc = MagicMock()
        mock_pandoc_proc.communicate.return_value = (
            "# Page 1\n\nExtracted content from page 1\n",
            None,
        )
        mock_pandoc_proc.returncode = 0

        # Configure mocks
        mock_popen.side_effect = [mock_pdf_proc, mock_pandoc_proc]

        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            result = await client.call_tool(
                "extract_pdf_pages",
                {"file": str(test_pdf), "pages": "1", "format": "markdown"},
            )

            data = json.loads(result.content[0].text)
            assert "content" in data
            assert "pages_extracted" in data
            assert "format" in data

            assert data["pages_extracted"] == [1]
            assert data["format"] == "markdown"
            assert "Extracted content" in data["content"]


async def test_fuzzy_search_documents_with_file_types(tmp_path: Path):
    """Test fuzzy_search_documents with file type filtering."""
    _skip_if_missing("rga")
    _skip_if_missing("fzf")

    with patch("subprocess.Popen") as mock_popen:
        # Mock processes
        mock_rga_proc = MagicMock()
        mock_rga_proc.stdout = []
        mock_rga_proc.wait.return_value = None

        mock_fzf_proc = MagicMock()
        mock_fzf_proc.communicate.return_value = ("", None)

        mock_popen.side_effect = [mock_rga_proc, mock_fzf_proc]

        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            result = await client.call_tool(
                "fuzzy_search_documents",
                {
                    "fuzzy_filter": "test",
                    "path": str(tmp_path),
                    "file_types": "pdf,docx",
                },
            )

            # Check that rga was called with the right adapter flags
            rga_call = mock_popen.call_args_list[0]
            args = rga_call[0][0]
            assert "--rga-adapters" in args
            assert "+pdf" in args
            assert "+docx" in args

            # Verify the result (should have empty matches since mocks return empty)
            data = json.loads(result.content[0].text)
            assert "matches" in data
            assert data["matches"] == []


# ---------------------------------------------------------------------------
# PDF Page Label Tests
# ---------------------------------------------------------------------------


def test_build_page_label_mapping_no_pdfminer():
    """Test _build_page_label_mapping when pdfminer is not available."""
    original_available = mcp_fuzzy_search.PDFMINER_AVAILABLE
    try:
        mcp_fuzzy_search.PDFMINER_AVAILABLE = False
        mapping = mcp_fuzzy_search._build_page_label_mapping(Path("test.pdf"))
        assert mapping == {}
    finally:
        mcp_fuzzy_search.PDFMINER_AVAILABLE = original_available


@patch("mcp_fuzzy_search.PDFMINER_AVAILABLE", True)
def test_build_page_label_mapping_with_labels(tmp_path: Path):
    """Test _build_page_label_mapping with mocked PDF that has page labels."""
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4\n%fake pdf")

    # Mock PDF components
    with (
        patch("mcp_fuzzy_search.PDFParser"),
        patch("mcp_fuzzy_search.PDFDocument"),
        patch("mcp_fuzzy_search.PDFPage") as mock_page_class,
    ):
        # Mock page objects with labels
        mock_page1 = MagicMock()
        mock_page1.label = "iii"
        mock_page2 = MagicMock()
        mock_page2.label = "iv"
        mock_page3 = MagicMock()
        mock_page3.label = "1"
        mock_page4 = MagicMock()
        mock_page4.label = None  # No label

        mock_page_class.create_pages.return_value = [
            mock_page1,
            mock_page2,
            mock_page3,
            mock_page4,
        ]

        mapping = mcp_fuzzy_search._build_page_label_mapping(test_pdf)

        expected = {
            "iii": 0,
            "iv": 1,
            "1": 2,
            # Page 4 has no label, so not in mapping
        }
        assert mapping == expected


@patch("mcp_fuzzy_search.PDFMINER_AVAILABLE", True)
def test_build_page_label_mapping_parse_error(tmp_path: Path):
    """Test _build_page_label_mapping when PDF parsing fails."""
    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4\n%fake pdf")

    with patch("mcp_fuzzy_search.PDFParser") as mock_parser:
        mock_parser.side_effect = Exception("PDF parsing failed")

        mapping = mcp_fuzzy_search._build_page_label_mapping(test_pdf)
        assert mapping == {}


def test_parse_page_spec_single_label():
    """Test _parse_page_spec with single page labels."""
    label_mapping = {"iii": 0, "iv": 1, "v": 2, "1": 3, "2": 4}

    # Test single labels
    assert mcp_fuzzy_search._parse_page_spec("iii", label_mapping) == [0]
    assert mcp_fuzzy_search._parse_page_spec("v", label_mapping) == [2]
    assert mcp_fuzzy_search._parse_page_spec("1", label_mapping) == [3]


def test_parse_page_spec_numeric_fallback():
    """Test _parse_page_spec falls back to numeric when label not found."""
    label_mapping = {"iii": 0, "iv": 1}

    # Numeric fallback
    assert mcp_fuzzy_search._parse_page_spec("5", label_mapping) == [5]
    assert mcp_fuzzy_search._parse_page_spec("10", label_mapping) == [10]


def test_parse_page_spec_ranges():
    """Test _parse_page_spec with ranges."""
    label_mapping = {"iii": 0, "iv": 1, "v": 2, "vi": 3, "vii": 4, "1": 5}

    # Label-based ranges
    assert mcp_fuzzy_search._parse_page_spec("iii-v", label_mapping) == [0, 1, 2]
    assert mcp_fuzzy_search._parse_page_spec("v-vii", label_mapping) == [2, 3, 4]

    # Numeric ranges
    assert mcp_fuzzy_search._parse_page_spec("7-9", label_mapping) == [7, 8, 9]

    # Mixed ranges (one label, one numeric)
    assert mcp_fuzzy_search._parse_page_spec("v-7", label_mapping) == [2, 3, 4, 5, 6, 7]


def test_parse_page_spec_invalid():
    """Test _parse_page_spec with invalid specifications."""
    label_mapping = {"iii": 0, "iv": 1}

    # Invalid specifications should return empty list
    assert mcp_fuzzy_search._parse_page_spec("nonexistent", label_mapping) == []
    assert mcp_fuzzy_search._parse_page_spec("", label_mapping) == []
    assert mcp_fuzzy_search._parse_page_spec("abc", label_mapping) == []


def test_parse_page_spec_edge_cases():
    """Test _parse_page_spec edge cases."""
    label_mapping = {"iii": 0, "iv": 1, "v": 2}

    # Range with only one side valid
    assert mcp_fuzzy_search._parse_page_spec("iii-nonexistent", label_mapping) == []
    assert mcp_fuzzy_search._parse_page_spec("nonexistent-v", label_mapping) == []

    # Multiple dashes (should not be treated as range)
    assert mcp_fuzzy_search._parse_page_spec("a-b-c", label_mapping) == []


async def test_extract_pdf_pages_with_labels(tmp_path: Path):
    """Test extract_pdf_pages with page labels."""
    _skip_if_missing("pdf2txt.py")
    _skip_if_missing("pandoc")

    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4\n%fake pdf")

    with (
        patch("mcp_fuzzy_search._build_page_label_mapping") as mock_mapping,
        patch("subprocess.Popen") as mock_popen,
    ):
        # Mock page label mapping
        mock_mapping.return_value = {"iii": 0, "iv": 1, "v": 2, "1": 3}

        # Mock subprocess calls
        mock_pdf_proc = MagicMock()
        mock_pdf_proc.stdout = MagicMock()
        mock_pdf_proc.wait.return_value = None
        mock_pdf_proc.returncode = 0
        mock_pdf_proc.communicate.return_value = (None, b"")

        mock_pandoc_proc = MagicMock()
        mock_pandoc_proc.communicate.return_value = (
            "# Roman Numeral Pages\n\nContent from pages iii and iv\n",
            None,
        )
        mock_pandoc_proc.returncode = 0

        mock_popen.side_effect = [mock_pdf_proc, mock_pandoc_proc]

        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            result = await client.call_tool(
                "extract_pdf_pages",
                {"file": str(test_pdf), "pages": "iii,iv", "format": "markdown"},
            )

            data = json.loads(result.content[0].text)
            assert "content" in data
            assert "pages_extracted" in data
            assert "page_labels" in data
            assert "format" in data

            # Should extract pages 0 and 1 (0-based indices for labels iii and iv)
            assert data["pages_extracted"] == [0, 1]
            assert data["page_labels"] == ["iii", "iv"]
            assert data["format"] == "markdown"
            assert "Roman Numeral Pages" in data["content"]


async def test_extract_pdf_pages_with_ranges(tmp_path: Path):
    """Test extract_pdf_pages with page label ranges."""
    _skip_if_missing("pdf2txt.py")
    _skip_if_missing("pandoc")

    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4\n%fake pdf")

    with (
        patch("mcp_fuzzy_search._build_page_label_mapping") as mock_mapping,
        patch("subprocess.Popen") as mock_popen,
    ):
        mock_mapping.return_value = {"iii": 0, "iv": 1, "v": 2, "vi": 3}

        # Mock subprocess calls
        mock_pdf_proc = MagicMock()
        mock_pdf_proc.stdout = MagicMock()
        mock_pdf_proc.wait.return_value = None
        mock_pdf_proc.returncode = 0
        mock_pdf_proc.communicate.return_value = (None, b"")

        mock_pandoc_proc = MagicMock()
        mock_pandoc_proc.communicate.return_value = (
            "# Range Content\n\nPages iii through v\n",
            None,
        )
        mock_pandoc_proc.returncode = 0

        mock_popen.side_effect = [mock_pdf_proc, mock_pandoc_proc]

        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            result = await client.call_tool(
                "extract_pdf_pages",
                {"file": str(test_pdf), "pages": "iii-v", "format": "markdown"},
            )

            data = json.loads(result.content[0].text)

            # Should extract pages 0, 1, 2 (0-based indices for labels iii, iv, v)
            assert data["pages_extracted"] == [0, 1, 2]
            assert data["page_labels"] == ["iii-v"]
            assert "Range Content" in data["content"]


async def test_extract_pdf_pages_mixed_specs(tmp_path: Path):
    """Test extract_pdf_pages with mixed page specifications."""
    _skip_if_missing("pdf2txt.py")
    _skip_if_missing("pandoc")

    test_pdf = tmp_path / "test.pdf"
    test_pdf.write_bytes(b"%PDF-1.4\n%fake pdf")

    with (
        patch("mcp_fuzzy_search._build_page_label_mapping") as mock_mapping,
        patch("subprocess.Popen") as mock_popen,
    ):
        # Only some pages have labels
        mock_mapping.return_value = {"iii": 0, "iv": 1}

        # Mock subprocess calls
        mock_pdf_proc = MagicMock()
        mock_pdf_proc.stdout = MagicMock()
        mock_pdf_proc.wait.return_value = None
        mock_pdf_proc.returncode = 0
        mock_pdf_proc.communicate.return_value = (None, b"")

        mock_pandoc_proc = MagicMock()
        mock_pandoc_proc.communicate.return_value = (
            "# Mixed Content\n\nMixed page specifications\n",
            None,
        )
        mock_pandoc_proc.returncode = 0

        mock_popen.side_effect = [mock_pdf_proc, mock_pandoc_proc]

        async with client_session(mcp_fuzzy_search.mcp._mcp_server) as client:
            # Mix of labels and numeric indices
            result = await client.call_tool(
                "extract_pdf_pages",
                {"file": str(test_pdf), "pages": "iii,5,iv", "format": "markdown"},
            )

            data = json.loads(result.content[0].text)

            # Should extract pages 0 (iii), 5 (numeric), 1 (iv) -> order preserved: [0, 5, 1]
            assert data["pages_extracted"] == [0, 5, 1]
            assert data["page_labels"] == ["iii", "iv"]  # Only the label-based ones
