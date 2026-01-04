# Fichero Workflow System - REVISED Architecture (Leveraging LangGraph)

**Revision Date:** 2026-01-04
**Status:** Architecture Revised to Use LangGraph Features
**Key Insight:** LangGraph has built-in checkpointing, MCP, durable execution - we should use them!

---

## Critical Architectural Revision

### What LangGraph Already Provides

LangGraph has **built-in capabilities** that eliminate the need for custom implementations:

1. ✅ **Checkpointing & Persistence**
   - `AsyncPostgresSaver` - Production-ready PostgreSQL checkpointing
   - `AsyncSqliteSaver` - Local development checkpointing
   - We can use **DuckDB** (we already have it!) via custom checkpointer
   - Automatic state management at every step

2. ✅ **Durable Execution**
   - Workflows automatically pause/resume using thread IDs
   - Fault tolerance built-in
   - Can resume after days/weeks
   - Start/stop/pause is native

3. ✅ **MCP Integration**
   - `langchain-mcp-adapters` library exists!
   - Connect to MCP servers: `MCPClient`
   - Use MCP tools in workflows natively
   - Expose workflows as MCP tools

4. ✅ **Human-in-the-Loop**
   - `interrupt()` function to pause workflows
   - `Command` primitive to resume with updates
   - State inspection at any point

### What We DON'T Need to Build

- ❌ Custom job queue system (LangGraph threads handle this)
- ❌ Custom checkpoint/state management (LangGraph checkpointer)
- ❌ Custom pause/resume logic (LangGraph durable execution)
- ❌ Custom MCP client (langchain-mcp-adapters exists)
- ❌ Manual state tracking (LangGraph does it automatically)

### What We DO Need to Build

- ✅ **Workflow Definitions Storage** - Save/load workflow graph definitions (JSON in DuckDB)
- ✅ **LangGraph Integration** - Configure checkpointer, thread management
- ✅ **Batch Execution Wrapper** - Iterate over documents, create thread per item
- ✅ **Activity Tracking** - High-level activity log (workflow started, completed, etc.)
- ✅ **UI Components** - Workflow library, activity monitor, comparison mode
- ✅ **API Layer** - REST API wrapping LangGraph operations

---

## Revised Architecture

### Backend Structure

```python
src/fichero/
├── workflows/
│   ├── builder.py              # EXISTING - builds LangGraph
│   ├── executor.py             # EXISTING - executes workflows
│   ├── registry.py             # EXISTING - tool registry
│   ├── persistence.py          # NEW - workflow definition CRUD
│   ├── checkpointer.py         # NEW - DuckDB checkpointer adapter
│   ├── batch.py                # NEW - batch execution wrapper
│   └── mcp_integration.py      # NEW - MCP tools via langchain-mcp-adapters
├── activities/                 # NEW - high-level activity tracking
│   ├── logger.py               # Activity logging
│   └── stream.py               # WebSocket streaming
└── api/routes/
    ├── workflows.py            # CRUD for workflow definitions
    ├── execution.py            # Execute workflows with threads
    └── activities.py           # Activity monitoring
```

### How LangGraph Execution Works

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from fichero.workflows.builder import build_graph

# 1. Load workflow definition from database
workflow_def = await load_workflow(workflow_id)

# 2. Build LangGraph
graph = build_graph(workflow_def)

# 3. Compile with checkpointer (uses DuckDB or PostgreSQL)
checkpointer = AsyncPostgresSaver(connection_string)
compiled = graph.compile(checkpointer=checkpointer)

# 4. Execute with thread ID (LangGraph handles state)
thread_id = f"workflow-{workflow_id}-{document_id}"
config = {"configurable": {"thread_id": thread_id}}

# This automatically checkpoints at every step!
result = await compiled.ainvoke(
    {"document_id": doc_id},
    config=config,
    durability="async"  # or "sync" for high durability
)

# 5. To resume later (even after crash):
result = await compiled.ainvoke(
    None,  # None means "resume from last checkpoint"
    config=config
)
```

### Batch Execution Pattern

```python
async def execute_batch(workflow_id: str, document_ids: list[str]):
    """Execute workflow on multiple documents using LangGraph threads."""

    workflow_def = await load_workflow(workflow_id)
    graph = build_graph(workflow_def)
    checkpointer = get_checkpointer()  # DuckDB-based
    compiled = graph.compile(checkpointer=checkpointer)

    # Create a thread for each document
    # LangGraph handles all state management!
    tasks = []
    for doc_id in document_ids:
        thread_id = f"batch-{workflow_id}-{doc_id}"
        config = {"configurable": {"thread_id": thread_id}}

        task = compiled.ainvoke(
            {"document_id": doc_id},
            config=config,
            durability="async"
        )
        tasks.append(task)

    # Run in parallel with concurrency limit
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return results
```

### MCP Integration (Built-in!)

```python
from langchain_mcp_adapters import MCPClient

# Connect to MCP server
async with MCPClient("npx", "-y", "mcp-server-name") as client:
    # Get tools from MCP server
    tools = await client.list_tools()

    # Add to workflow registry automatically
    for tool in tools:
        register_mcp_tool(tool)

    # Now workflows can use MCP tools!
```

---

## Revised Phase Breakdown

### Phase 0: Quick Win (1-2 days)
**TODO-063**: Increase window size (unchanged)

---

### Phase 1: LangGraph Integration & Persistence (2-3 weeks)

#### Backend Tasks (3-4 days)
**TODO-064**: Configure LangGraph Checkpointing
- Install `langgraph-checkpoint-postgres` or `langgraph-checkpoint-sqlite`
- Create DuckDB-based checkpointer adapter (or use SQLite)
- Configure AsyncPostgresSaver for production
- Test checkpointing with simple workflow
- Unit tests for checkpointer

**TODO-065**: Workflow Definition Persistence
- Database schema for workflow definitions (just the graph JSON)
- Pydantic models for WorkflowDef
- CRUD operations: create, read, update, delete
- Import/export as JSON
- Unit tests

**TODO-066**: Execution API with Thread Management
- POST /api/workflows/execute - Execute with thread ID
- GET /api/workflows/threads/{thread_id} - Get thread state
- POST /api/workflows/threads/{thread_id}/resume - Resume execution
- POST /api/workflows/threads/{thread_id}/cancel - Cancel execution
- Unit tests

#### Frontend Tasks (2-3 days)
**TODO-067**: Workflow Library UI
- List saved workflows
- Save current workflow
- Load workflow
- Delete workflow
- SwiftUI only

**TODO-068**: Integration Testing
- End-to-end workflow save/load/execute
- Test checkpoint/resume
- Test thread management

---

### Phase 2: Batch Execution & Activity Tracking (2-3 weeks)

#### Backend Tasks (3-4 days)
**TODO-069**: Batch Execution System
- Batch execution wrapper using LangGraph threads
- One thread per document
- Progress tracking via checkpoint queries
- Concurrency control
- Unit tests

**TODO-070**: Activity Tracking
- High-level activity log (workflow started, node completed, etc.)
- Query LangGraph checkpoints for detailed state
- WebSocket streaming for real-time updates
- Unit tests

#### Frontend Tasks (2-3 days)
**TODO-071**: Activity Monitor UI
- Real-time activity stream
- Progress visualization
- Thread state inspection
- SwiftUI only

**TODO-072**: Integration Testing
- Batch execution with 100+ files
- Real-time progress updates
- Pause/resume workflows

---

### Phase 3: MCP Integration (1-2 weeks)

**Much Simpler with langchain-mcp-adapters!**

#### Backend Tasks (2-3 days)
**TODO-073**: MCP Client Integration
- Install `langchain-mcp-adapters`
- Connect to MCP servers
- Load tools dynamically
- Register MCP tools in workflow registry
- Unit tests

**TODO-074**: MCP Server Exposure
- Expose Fichero workflows as MCP tools
- Create MCP server using `mcp` library
- Tool schema generation
- Unit tests

#### Frontend Tasks (1-2 days)
**TODO-075**: MCP Configuration UI
- MCP server connection settings
- Tool listing
- SwiftUI only

**TODO-076**: Integration Testing
- Test with real MCP servers
- Test Fichero as MCP server

---

### Phase 4: Advanced Features (2-3 weeks)

#### Workflow Chaining (1 day)
**TODO-077**: SubWorkflow Tool
- Create SubWorkflow tool in registry
- Execute nested workflows with LangGraph subgraphs
- Unit tests

#### Model Comparison (2-3 days)
**TODO-078**: Comparison Engine
- Execute same workflow on multiple models in parallel
- Cost/time tracking
- Result aggregation
- Unit tests

**TODO-079**: Comparison UI
- Model selection
- Side-by-side results
- SwiftUI only

#### Automation (3-4 days)
**TODO-080**: Scheduler
- APScheduler integration
- Schedule workflows with thread IDs
- Unit tests

**TODO-081**: File System Triggers
- Watchdog integration
- Trigger workflow execution
- Unit tests

**TODO-082**: Automation UI
- Schedule management
- Trigger configuration
- SwiftUI only

#### Action Library (2 days)
**TODO-083**: Action Library
- Store workflow templates
- Quick actions (single-node workflows)
- Unit tests

**TODO-084**: Action Library UI
- Action picker
- Drag-and-drop to canvas
- SwiftUI only

---

## Database Schema (Simplified!)

### workflows table (Workflow Definitions Only!)
```sql
CREATE TABLE workflows (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    nodes JSON NOT NULL,        -- Graph definition
    edges JSON NOT NULL,        -- Graph definition
    metadata JSON,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### LangGraph Checkpoints
**LangGraph handles these tables automatically via checkpointer!**
- `checkpoints` - State snapshots
- `checkpoint_writes` - Pending writes
- `checkpoint_metadata` - Thread metadata

We just query them, don't create them ourselves.

### activities table (High-Level Tracking)
```sql
CREATE TABLE activities (
    id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES workflows(id),
    thread_id TEXT NOT NULL,    -- LangGraph thread
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    metadata JSON,
    created_at TIMESTAMP
);
```

### schedules & triggers (Same as before)
```sql
CREATE TABLE schedules (
    id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES workflows(id),
    schedule_config JSON,
    enabled BOOLEAN,
    created_at TIMESTAMP
);

CREATE TABLE triggers (
    id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES workflows(id),
    trigger_config JSON,
    enabled BOOLEAN,
    created_at TIMESTAMP
);
```

---

## Key Technical Changes

### 1. No Custom Job System
**Before**: Build custom job queue with state management
**After**: Use LangGraph threads - one thread per execution

### 2. Checkpointing is Built-in
**Before**: Custom checkpoint/resume logic
**After**: LangGraph handles automatically with `durability` mode

### 3. MCP is Native
**Before**: Build custom MCP client
**After**: Use `langchain-mcp-adapters.MCPClient`

### 4. State is Managed by LangGraph
**Before**: Track execution state in custom database
**After**: Query LangGraph checkpoints for state

### 5. Pause/Resume is Native
**Before**: Build custom pause/resume
**After**: Use `interrupt()` and resume with same thread ID

---

## Execution Patterns

### Single Document Execution
```python
# Create thread
thread_id = f"doc-{document_id}"
config = {"configurable": {"thread_id": thread_id}}

# Execute (automatically checkpoints)
result = await graph.ainvoke(inputs, config=config)
```

### Batch Execution
```python
# One thread per document
for doc_id in document_ids:
    thread_id = f"batch-{job_id}-{doc_id}"
    config = {"configurable": {"thread_id": thread_id}}
    await graph.ainvoke({"document_id": doc_id}, config=config)
```

### Resume After Failure
```python
# Same thread ID, None input = resume
result = await graph.ainvoke(None, config=config)
```

### Human-in-the-Loop
```python
from langgraph.types import interrupt

def review_node(state):
    # Pause for human review
    user_input = interrupt("Please review this content")
    return {"reviewed": user_input}
```

---

## Timeline (Revised - Much Faster!)

- **Phase 0**: 1-2 days (window size)
- **Phase 1**: 2-3 weeks (LangGraph integration + persistence)
- **Phase 2**: 2-3 weeks (batch execution + activity tracking)
- **Phase 3**: 1-2 weeks (MCP - much simpler with adapters!)
- **Phase 4**: 2-3 weeks (advanced features)

**Total**: 7-11 weeks (down from 10-14 weeks!)

---

## Success Criteria

### Phase 1
- ✅ Workflows persist as definitions in DuckDB
- ✅ LangGraph checkpointing works
- ✅ Can execute workflow with thread ID
- ✅ Can resume workflow from checkpoint
- ✅ Import/export workflows

### Phase 2
- ✅ Batch execution on 100+ files
- ✅ Real-time progress via activity monitor
- ✅ Can pause/resume batch jobs
- ✅ Thread state visible in UI

### Phase 3
- ✅ MCP tools load dynamically
- ✅ Workflows can use MCP tools
- ✅ Fichero exposed as MCP server
- ✅ External agents can trigger Fichero

### Phase 4
- ✅ Workflow chaining works
- ✅ Model comparison with 5+ models
- ✅ Scheduled workflows execute
- ✅ File triggers work
- ✅ Action library has 10+ actions

---

## Next Steps

1. **Review revised architecture** - Confirm LangGraph approach
2. **Start Phase 0** - Window size (quick win)
3. **Prototype checkpointing** - Test LangGraph with DuckDB checkpointer
4. **Begin Phase 1** - LangGraph integration

---

## References

- **LangGraph Persistence**: https://langchain-ai.github.io/langgraph/concepts/persistence/
- **Durable Execution**: https://langchain-ai.github.io/langgraph/concepts/durable_execution/
- **MCP Integration**: https://langchain-ai.github.io/langgraph/concepts/mcp/
- **langchain-mcp-adapters**: https://github.com/langchain-ai/langchain-mcp-adapters
- **LangGraph Checkpointers**: https://langchain-ai.github.io/langgraph/reference/checkpoints/

---

**Status**: Architecture revised to leverage LangGraph properly - much simpler!
