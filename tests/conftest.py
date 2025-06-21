import sys

import pytest
from mcp.client.session import ClientSession
from mcp.client.stdio import StdioServerParameters, stdio_client


@pytest.fixture
async def cli_client():
    """
    Optional fixture for testing the packaged script end-to-end.
    This runs the script as a subprocess with stdio transport.
    """
    server_params = StdioServerParameters(
        command=sys.executable, args=["mcp_fd_server.py"]
    )

    async with stdio_client(server_params) as streams:
        read_stream, write_stream = streams
        client_session = ClientSession(read_stream, write_stream)
        await client_session.initialize()
        yield client_session
