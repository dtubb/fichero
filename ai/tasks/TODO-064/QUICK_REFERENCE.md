# TODO-064: DuckDB Checkpointer Quick Reference

## Usage

```python
from fichero.workflows.checkpointer import get_checkpointer
from langgraph.graph import StateGraph, END

# Get checkpointer (uses default Fichero database)
checkpointer = get_checkpointer()

# Build your workflow
workflow = StateGraph(YourState)
workflow.add_node("step1", your_function)
workflow.add_edge("step1", END)

# Compile with checkpointer
app = workflow.compile(checkpointer=checkpointer)

# Execute with thread ID
config = {"configurable": {"thread_id": "unique-id"}}
result = await app.ainvoke(input_data, config=config)

# Resume from last checkpoint
resumed = await app.ainvoke(None, config=config)
```

## Key Features

- ✅ **Durable execution**: Workflows survive crashes/restarts
- ✅ **Pause/resume**: Use `interrupt_before` to pause workflows
- ✅ **Thread isolation**: Parallel workflows don't interfere
- ✅ **Checkpoint history**: Time-travel debugging
- ✅ **Single database**: All data in one DuckDB file

## Database Schema

**checkpoints** table stores workflow execution state:
- `thread_id` - Unique ID for workflow execution
- `checkpoint_id` - Unique ID for this checkpoint
- `parent_checkpoint_id` - Links to previous checkpoint
- `checkpoint` - Serialized workflow state (BLOB)
- `metadata` - Serialized metadata (BLOB)

**checkpoint_writes** table stores pending writes:
- Links to checkpoint via `thread_id` + `checkpoint_id`
- Stores channel updates as serialized BLOBs

## Testing

```bash
# Run unit tests (18 tests)
PYTHONPATH=src .venv/bin/pytest tests/unit/workflows/test_checkpointer.py -v

# Run integration tests (6 tests)
PYTHONPATH=src .venv/bin/pytest tests/unit/workflows/test_checkpointer_integration.py -v

# Run all workflow tests (24 tests)
PYTHONPATH=src .venv/bin/pytest tests/unit/workflows/ -v
```

## Files

- `src/fichero/workflows/checkpointer.py` - Main implementation (437 lines)
- `tests/unit/workflows/test_checkpointer.py` - Unit tests (487 lines)
- `tests/unit/workflows/test_checkpointer_integration.py` - Integration tests (272 lines)

## Next Steps

See TODO-065 for workflow definition persistence.
