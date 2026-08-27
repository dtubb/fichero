# fichero-mcp

MCP server for Fichero — exposes a running Fichero server's document, search,
workflow, and knowledge tools to AI clients over MCP. A thin wrapper over
`FicheroClient`: every tool is one HTTP call.

Entry points: `fichero-mcp` (full surface, ~29 tools) and
`fichero-mcp-simple` (minimal).

## Connecting

Zero setup against the running Fichero app: when nothing answers on the
TCP port, the client dials the app's own Unix socket automatically. A
`FICHERO_API_URL` env or `--api-url` targets a specific server instead;
`FICHERO_UDS=0` disables the socket probe.

## Libraries

The server starts with NO library bound. Call `fichero_list_libraries` to
see every library the engine knows, then `fichero_use_library` with a
`.fichero` path to scope the session; all library-scoped tools (documents,
search, workflows, knowledge graph) use it from then on. Alternatively
pin one library for the whole session with `--library-path` or
`FICHERO_LIBRARY_PATH`.

## Example: Claude Code

```bash
claude mcp add fichero -- fichero-mcp
```
