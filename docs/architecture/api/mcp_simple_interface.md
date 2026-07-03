# Simplified MCP Interface (`fichero-mcp-simple`)

Issue: #1327

`fichero-mcp-simple` provides a small, stable outside-agent surface (10 tools)
for the core loop: read library -> run workflow -> query KG -> save notes.

## Start Server

```bash
python -m fichero.mcp_simple --api-url http://127.0.0.1:8765 --library-path /path/to/Library.fichero
```

## Tool Contract

1. `health()`
2. `list_documents(input: ListDocumentsInput)`
3. `get_document(input: DocumentIdInput)`
4. `run_workflow(input: RunWorkflowInput)`
5. `workflow_status(input: WorkflowStatusInput)`
6. `list_artifacts(input: ArtifactsInput)`
7. `kg_search(input: KGSearchInput)`
8. `kg_claims(input: KGClaimsInput)`
9. `create_note(input: CreateNoteInput)`
10. `list_notes(input: ListNotesInput)`

All non-trivial tools use typed Pydantic input schemas; the MCP server exposes
these schemas in each tool's `inputSchema`.

## Current `/api/mcp/tools` hardening

The shipped MCP story on current `main` has two distinct surfaces:

- `python -m fichero.mcp_simple` and `python -m fichero.mcp_server` are stdio
  MCP servers that call the typed `FicheroClient`.
- `fichero-engine/src/fichero/api/routes/mcp_tools.py` is a separate FastAPI
  REST adapter mounted at `/api/mcp/tools` from `api/main.py`.

That REST adapter is now hardened in a few specific ways:

- router-level auth is required through
  `Depends(_require_authenticated_or_bootstrap)`
- read routes use `get_library_database`, while mutation routes use
  `get_library_database_for_write`
- request bodies such as `KnowledgeEntityUpsertRequest` and
  `KnowledgeClaimCreateRequest` declare `extra="forbid"`
- bounded input lengths are enforced on the body models with `Field(...)`
- the list routes bound search/filter/pagination inputs with `Query(...)`,
  including `q` length caps and `limit`/`offset` ranges

The route family currently exposed under `/api/mcp/tools` is narrowly scoped to
knowledge-graph entity/claim CRUD-style adapters:

- `POST /api/mcp/tools/knowledge/entities/upsert`
- `GET|DELETE /api/mcp/tools/knowledge/entities/{entity_id}`
- `GET /api/mcp/tools/knowledge/entities`
- `POST /api/mcp/tools/knowledge/claims/create`
- `GET|DELETE /api/mcp/tools/knowledge/claims/{claim_id}`
- `GET /api/mcp/tools/knowledge/claims`

What this does **not** mean yet: these REST adapter writes are not fully folded
onto the action registry. On current `main`, the mutation handlers in
`mcp_tools.py` still persist directly with `db.save(...)` / `db.delete(...)`.
So the shipped hardening here is authentication + validation + bounded adapter
inputs, not full audit-path normalization. That remaining convergence is still
planned.

## Example Calls

```json
{"tool": "list_documents", "arguments": {"input": {"limit": 20, "doc_type": "pdf"}}}
```

```json
{"tool": "run_workflow", "arguments": {"input": {"workflow_id": "catalogue", "doc_id": "doc-123"}}}
```

```json
{"tool": "kg_search", "arguments": {"input": {"query": "Leibniz", "limit": 10}}}
```

```json
{"tool": "create_note", "arguments": {"input": {"title": "Observation", "body": "Claim needs verification", "linked_claim_ids": ["claim-1"]}}}
```
