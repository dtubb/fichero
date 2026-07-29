"""Fichero MCP server — exposes a running Fichero server's tools over MCP.

A thin client product: every tool is one `FicheroClient` HTTP call against a
running fichero-server. Split out of the server package in #4227. The MCP
*client* manager the server uses for workflow tools stays server-side
(`fichero_server.mcp.manager`); this package is the MCP *server* shipped to
AI clients.
"""
