# fichero-mcp

MCP server for Fichero — exposes a running Fichero server's document, search,
and knowledge tools to AI clients over MCP. A thin wrapper over
`FicheroClient`: every tool is one HTTP call.

Entry points: `fichero-mcp` (full surface) and `fichero-mcp-simple`. Both
connect to a running fichero-server; see `fichero-server/README.md`.
