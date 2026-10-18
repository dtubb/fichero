"""A real MCP server for the client round-trip test: FastMCP over stdio with one `echo` tool."""
from mcp.server.fastmcp import FastMCP

server = FastMCP("echoer")


@server.tool()
def echo(text: str) -> str:
    """Say the text back."""
    return f"echo: {text}"


if __name__ == "__main__":
    server.run()
