"""A real MCP server for the client round-trip test: FastMCP over stdio. `echo` says it only reads; `shout` does not say."""
from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

server = FastMCP("echoer")


@server.tool(annotations=ToolAnnotations(readOnlyHint=True))
def echo(text: str) -> str:
    """Say the text back."""
    return f"echo: {text}"


@server.tool()
def shout(text: str) -> str:
    """Say the text back loudly (the server does not mark this tool read-only)."""
    return f"SHOUT: {text.upper()}"


if __name__ == "__main__":
    server.run()
