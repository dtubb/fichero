# TODO-066: Execution API Quick Reference

## API Endpoints

All endpoints require `X-Fichero-Library-Path` header with path to .fichero package.

### Execute Workflow
```bash
POST /api/workflow-execution/execute
```

Request:
```json
{
  "workflow_id": "abc123",
  "inputs": {"text": "Hello"},
  "thread_id": "optional-custom-id",
  "checkpoint_ns": "",
  "interrupt_before": ["node2"],
  "interrupt_after": []
}
```

Response:
```json
{
  "thread_id": "thread-a1b2c3",
  "workflow_id": "abc123",
  "workflow_name": "My Workflow",
  "status": "paused",
  "checkpoint_id": "checkpoint-xyz",
  "current_state": {...},
  "error": null
}
```

### Resume Workflow
```bash
POST /api/workflow-execution/threads/{thread_id}/resume
```

Request (optional):
```json
{
  "inputs": {"new_data": "value"}
}
```

### Get Status
```bash
GET /api/workflow-execution/threads/{thread_id}/status
```

Response: Same as execute response

### List Threads
```bash
GET /api/workflow-execution/threads?limit=100
```

Response:
```json
{
  "threads": [
    {
      "thread_id": "thread-1",
      "workflow_id": "abc",
      "workflow_name": "Workflow 1",
      "status": "completed",
      ...
    }
  ]
}
```

### Delete Thread
```bash
DELETE /api/workflow-execution/threads/{thread_id}
```

Response:
```json
{
  "message": "Thread deleted: thread-a1b2c3"
}
```

## Status Values

- `"running"` - Currently executing
- `"paused"` - Stopped at interrupt point
- `"completed"` - Finished successfully
- `"failed"` - Error occurred

## Usage with curl

```bash
# Start backend
PYTHONPATH=src .venv/bin/uvicorn fichero.api.main:app --port 8765

# Execute workflow
curl -X POST "http://localhost:8765/api/workflow-execution/execute" \
  -H "Content-Type: application/json" \
  -H "X-Fichero-Library-Path: /Users/name/MyLibrary.fichero" \
  -d '{"workflow_id": "abc123", "inputs": {}}'

# Resume
curl -X POST "http://localhost:8765/api/workflow-execution/threads/thread-abc/resume" \
  -H "X-Fichero-Library-Path: /Users/name/MyLibrary.fichero"

# Status
curl "http://localhost:8765/api/workflow-execution/threads/thread-abc/status" \
  -H "X-Fichero-Library-Path: /Users/name/MyLibrary.fichero"
```

## Files

- `src/fichero/api/routes/workflow_execution.py` - Main implementation (480 lines)
- `src/fichero/api/main.py` - Router registration

## Integration

Uses:
- `AsyncDuckDBCheckpointer` from TODO-064
- `WorkflowStore` from TODO-065
- `fichero.workflows.builder._make_node_function`
- `fichero.workflows.registry.get_tool`

## Next Steps

See TODO-067 for SwiftUI workflow library UI.
See TODO-068 for integration testing.
