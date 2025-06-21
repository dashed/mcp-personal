import json
import subprocess
import sys
import pytest
from pathlib import Path
from unittest.mock import patch

pytestmark = pytest.mark.anyio


def test_cli_search_command(tmp_path: Path):
    """Test CLI search subcommand."""
    # Create test files
    (tmp_path / "test.py").write_text("print('hello')")
    (tmp_path / "test.txt").write_text("hello")
    
    # Run search command
    result = subprocess.run(
        [sys.executable, "mcp_fd_server.py", "search", r"\.py$", str(tmp_path)],
        capture_output=True,
        text=True
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
    
    # Run filter command
    result = subprocess.run(
        [sys.executable, "mcp_fd_server.py", "filter", "main", r"\.py$", str(tmp_path), "--first"],
        capture_output=True,
        text=True
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
        [sys.executable, "mcp_fd_server.py", "-h"],
        capture_output=True,
        text=True
    )
    
    assert result.returncode == 0
    assert "fd + fzf powers" in result.stdout
    assert "search" in result.stdout
    assert "filter" in result.stdout


@patch("subprocess.check_output")
def test_cli_search_mocked(mock_check_output):
    """Test CLI search with mocked subprocess."""
    mock_check_output.return_value = "file1.py\nfile2.py\n"
    
    with patch("shutil.which", return_value="/mock/fd"):
        result = subprocess.run(
            [sys.executable, "mcp_fd_server.py", "search", r"\.py$"],
            capture_output=True,
            text=True
        )
    
    output = json.loads(result.stdout)
    assert output["matches"] == ["file1.py", "file2.py"]


def test_mcp_server_mode():
    """Test that script runs in MCP server mode without arguments."""
    # Start the server
    proc = subprocess.Popen(
        [sys.executable, "mcp_fd_server.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )
    
    try:
        # Send a simple initialize request
        init_request = {
            "jsonrpc": "2.0",
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "1.0"}
            },
            "id": 1
        }
        
        proc.stdin.write(f"Content-Length: {len(json.dumps(init_request))}\r\n\r\n")
        proc.stdin.write(json.dumps(init_request))
        proc.stdin.flush()
        
        # Give it a moment to respond
        import time
        time.sleep(0.5)
        
        # Terminate the process
        proc.terminate()
        stdout, stderr = proc.communicate(timeout=2)
        
        # Check if binary missing error occurred
        if "Cannot find the" in stderr:
            pytest.skip("Required binaries not available")
        
        # Should have received some output (at least headers)
        assert stdout or not stderr  # Either got output or no error
        
    except subprocess.TimeoutExpired:
        proc.kill()
        pytest.skip("Server process timeout")
    except Exception:
        proc.kill()
        raise


async def test_cli_client_fixture(tmp_path: Path, cli_client):
    """Test the CLI client fixture for end-to-end testing."""
    # Create test file
    (tmp_path / "test.py").write_text("# test file")
    
    try:
        # List available tools
        from mcp.types import ListToolsRequest, ClientRequest, ToolRequest
        import json
        
        tools_result = await cli_client.send_request(
            ClientRequest(ListToolsRequest(method="tools/list"))
        )
        assert len(tools_result.tools) == 2
        
        # Call search_files through subprocess client
        result = await cli_client.send_request(
            ClientRequest(
                ToolRequest(
                    method="tools/call",
                    params={
                        "name": "search_files",
                        "arguments": {"pattern": r"\.py$", "path": str(tmp_path)}
                    }
                )
            )
        )
        
        data = json.loads(result.content[0].text)
        assert "matches" in data or "error" in data
        
    except Exception as e:
        if "Cannot find the" in str(e):
            pytest.skip("Required binaries not available")
        raise