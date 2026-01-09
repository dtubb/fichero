# TODO-065: Workflow Persistence Quick Reference

## Usage

```python
from fichero.workflows.workflow_store import get_workflow_store
from fichero.models import Workflow

# Get store (uses default Fichero database)
store = get_workflow_store()

# Create and save workflow
workflow = Workflow(
    name="Transcribe Documents",
    format="nodes",
    nodes=[
        {"id": "node1", "tool": "transcribe", "label": "Transcribe"},
        {"id": "node2", "tool": "summarize", "label": "Summarize"}
    ],
    edges=[
        {"source_node_id": "node1", "target_node_id": "node2"}
    ],
    folder_path="/audio",
    tags=["transcription", "audio"]
)
store.save(workflow)

# Retrieve workflow
workflow = store.get(workflow_id)

# List all workflows
workflows = store.list_all()

# Export to JSON
json_str = store.export_workflow(workflow_id)

# Import from JSON
imported = store.import_workflow(json_str, new_id=True)
```

## Key Features

- ✅ **CRUD operations**: Save, get, delete workflows
- ✅ **Organization**: Folders, sort order, templates
- ✅ **Search**: By name, tags, provider
- ✅ **Import/Export**: JSON with full portability
- ✅ **Bulk operations**: Export/import multiple workflows
- ✅ **DuckDB storage**: Single database for all data

## API Reference

### CRUD
- `save(workflow)` - Save or update workflow
- `get(workflow_id)` - Get workflow by ID
- `delete(workflow_id)` - Delete workflow
- `duplicate(workflow_id, new_name)` - Create copy with new ID

### Listing
- `list_all(folder_path=None)` - List workflows (optional folder filter)
- `list_templates()` - List workflow templates only

### Search
- `search(name=None, tags=None, provider=None)` - Search workflows

### Organization
- `update_folder(workflow_id, folder_path)` - Move to folder
- `update_sort_order(workflow_id, sort_order)` - Set display order

### Import/Export
- `export_workflow(workflow_id)` → JSON string
- `import_workflow(json_str, new_id=True, folder_path=None)` → Workflow
- `export_to_file(workflow_id, file_path)` - Write JSON file
- `import_from_file(file_path)` - Read JSON file

### Bulk
- `export_all(folder_path=None)` → JSON array
- `import_all(json_str, new_ids=True, folder_path=None)` → List[Workflow]

## Database Schema

Workflows stored in `workflows` table (auto-created from Pydantic model):
- `id` - Unique workflow ID
- `name` - Workflow name
- `description` - Optional description
- `format` - "steps" or "nodes"
- `nodes` - Visual workflow nodes (JSON)
- `edges` - Node connections (JSON)
- `folder_path` - Organization folder (Unix-style)
- `sort_order` - Display order within folder
- `is_template` - Template flag
- `tags` - Categorization tags (JSON array)
- `provider`, `model` - LLM configuration
- `created_at`, `updated_at` - Timestamps

## Testing

```bash
# Run workflow store tests (41 tests)
PYTHONPATH=src .venv/bin/pytest tests/unit/workflows/test_workflow_store.py -v

# Run all workflow tests (65 tests)
PYTHONPATH=src .venv/bin/pytest tests/unit/workflows/ -v
```

## Files

- `src/fichero/workflows/workflow_store.py` - Main implementation (397 lines)
- `tests/unit/workflows/test_workflow_store.py` - Unit tests (630 lines, 41 tests)

## Next Steps

See TODO-066 for execution API with thread management.
