import pytest
import anyio
from mcp.client.session import ClientSession
from mcp.shared.memory import create_client_server_memory_streams
from mcp.server import Server
import mcp_fd_server


@pytest.fixture
async def client():
    """
    A live FastMCP client that talks to the *in-memory* server instance
    defined inside mcp_fd_server.py (variable `mcp`).
    """
    # Get the internal MCP server from FastMCP
    server = mcp_fd_server.mcp._mcp_server
    
    async with create_client_server_memory_streams() as (client_streams, server_streams):
        client_read, client_write = client_streams
        server_read, server_write = server_streams
        
        async with anyio.create_task_group() as tg:
            # Start server
            async def run_server():
                await server.run(
                    server_read,
                    server_write,
                    server.create_initialization_options(),
                    raise_exceptions=True,
                )
            
            tg.start_soon(run_server)
            
            # Create and initialize client
            client_session = ClientSession(client_read, client_write)
            await client_session.initialize()
            
            yield client_session
            
            # Cleanup
            tg.cancel_scope.cancel()


@pytest.fixture
async def cli_client():
    """
    Optional fixture for testing the packaged script end-to-end.
    This runs the script as a subprocess with stdio transport.
    """
    import sys
    from mcp.client.stdio import StdioServerParameters, stdio_client
    
    server_params = StdioServerParameters(
        command=sys.executable,
        args=["mcp_fd_server.py"]
    )
    
    async with stdio_client(server_params) as streams:
        read_stream, write_stream = streams
        client_session = ClientSession(read_stream, write_stream)
        await client_session.initialize()
        yield client_session