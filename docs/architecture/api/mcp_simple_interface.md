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
