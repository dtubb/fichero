# Fichero Workflow System - FINAL Architecture

**Date**: January 4, 2026
**Status**: Complete architecture leveraging all LangGraph capabilities

---

## The Big Revelation

LangGraph provides **everything** we need:

1. ✅ **Checkpointing** - PostgreSQL/SQLite/DuckDB persistence
2. ✅ **Durable Execution** - Automatic pause/resume with threads
3. ✅ **MCP Integration** - `langchain-mcp-adapters` built-in
4. ✅ **Agents** - `create_react_agent`, supervisor, swarm patterns
5. ✅ **Human-in-the-Loop** - Native interrupt system
6. ✅ **Memory** - `langmem` for short/long-term memory
7. ✅ **Streaming** - Real-time state, tokens, tool outputs
8. ✅ **Multi-Agent** - Supervisor and swarm patterns built-in

We just need to:
- Store workflow definitions (JSON in DuckDB)
- Configure LangGraph properly
- Build UI layer
- Create batch execution wrapper

---

## What We're Actually Building

### 1. Workflow Definition Storage
Save/load workflow graph definitions as JSON in DuckDB.

### 2. LangGraph Integration Layer
- Configure checkpointer (DuckDB-based)
- Thread management
- Batch execution wrapper

### 3. Agent & Tool System
- Use `create_react_agent` for agent nodes
- Load MCP tools via `langchain-mcp-adapters`
- Register internal tools
- Multi-agent collaboration with supervisor/swarm

### 4. Activity Tracking
High-level activity log (workflow started, completed, etc.)
Query LangGraph checkpoints for detailed state.

### 5. UI Components
- Workflow library
- Activity monitor
- Comparison mode
- Automation interface

---

## Complete Architecture

### Backend Structure
```
src/fichero/
├── workflows/
│   ├── builder.py              # EXISTING - builds LangGraph
│   ├── executor.py             # EXISTING - executes workflows
│   ├── registry.py             # EXISTING - tool registry
│   ├── persistence.py          # NEW - workflow def CRUD
│   ├── checkpointer.py         # NEW - DuckDB checkpointer
│   ├── batch.py                # NEW - batch execution wrapper
│   ├── agents.py               # NEW - agent node creation
│   └── mcp_integration.py      # NEW - MCP via langchain-mcp-adapters
├── activities/                 # NEW - activity tracking
│   ├── logger.py
│   └── stream.py               # WebSocket streaming
├── automation/                 # NEW - scheduling
│   ├── scheduler.py            # APScheduler
│   └── triggers.py             # File watchers
└── api/routes/
    ├── workflows.py            # Workflow CRUD
    ├── execution.py            # Execute with threads
    ├── activities.py           # Activity monitoring
    ├── comparison.py           # Model comparison
    └── automation.py           # Schedules/triggers
```

### Frontend Structure
```
Fichero/Fichero/
├── Views/
│   ├── Workflow/
│   │   ├── WorkflowEditor.swift       # EXISTING - canvas
│   │   ├── WorkflowListView.swift     # NEW - saved workflows
│   │   ├── AgentNodeEditor.swift      # NEW - agent config
│   │   └── ActionLibrary.swift        # NEW - action picker
│   ├── Sidebar/
│   │   ├── CompareMode.swift          # NEW - comparison
│   │   └── AutomationMode.swift       # NEW - schedules/triggers
│   ├── Activities/
│   │   └── ActivityMonitor.swift      # NEW - real-time monitor
│   └── Automation/
│       └── SchedulerView.swift        # NEW - automation UI
└── Services/
    ├── WorkflowService.swift          # NEW - workflow API
    ├── ActivityService.swift          # NEW - activity tracking
    └── WebSocketService.swift         # NEW - real-time updates
```

---

## Key Patterns

### 1. Agent Nodes in Workflows

```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

def create_agent_node(agent_config):
    """Create an agent node for workflow."""
    model = ChatOpenAI(model=agent_config["model"])
    tools = load_tools(agent_config["tools"])

    # Create ReAct agent
    agent = create_react_agent(model, tools=tools)

    # Wrap as workflow node
    def agent_node(state):
        result = agent.invoke({"messages": state["messages"]})
        return {"messages": result["messages"]}

    return agent_node
```

### 2. Multi-Agent Workflows

```python
from langgraph_supervisor import create_supervisor

# Create supervisor agent
supervisor = create_supervisor(
    model=ChatOpenAI("gpt-4"),
    agents={
        "researcher": researcher_agent,
        "writer": writer_agent,
        "reviewer": reviewer_agent
    }
)

# Use in workflow
graph.add_node("supervisor", supervisor)
```

### 3. MCP Tool Loading

```python
from langchain_mcp_adapters import MCPClient

async def load_mcp_tools(server_config):
    """Load tools from MCP server."""
    async with MCPClient(server_config["command"]) as client:
        tools = await client.list_tools()

        # Convert to LangChain tools
        for tool in tools:
            langchain_tool = await client.get_tool(tool.name)
            register_tool(tool.name, langchain_tool)
```

### 4. Workflow with Checkpointing

```python
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

# Build workflow
graph = build_graph(workflow_def)

# Configure checkpointer
checkpointer = AsyncPostgresSaver(conn_string)

# Compile with checkpointing
compiled = graph.compile(
    checkpointer=checkpointer,
    durability="async"  # or "sync" for high durability
)

# Execute with thread
thread_id = f"workflow-{workflow_id}-{doc_id}"
config = {"configurable": {"thread_id": thread_id}}

result = await compiled.ainvoke(
    {"document_id": doc_id},
    config=config
)
```

### 5. Batch Execution

```python
async def execute_batch(workflow_id, document_ids):
    """Execute workflow on multiple documents."""
    compiled = await load_and_compile_workflow(workflow_id)

    async def process_document(doc_id):
        thread_id = f"batch-{workflow_id}-{doc_id}"
        config = {"configurable": {"thread_id": thread_id}}

        try:
            result = await compiled.ainvoke(
                {"document_id": doc_id},
                config=config
            )
            await log_activity("completed", workflow_id, thread_id)
            return result
        except Exception as e:
            await log_activity("failed", workflow_id, thread_id, str(e))
            return None

    # Process with concurrency limit
    semaphore = asyncio.Semaphore(4)

    async def limited_process(doc_id):
        async with semaphore:
            return await process_document(doc_id)

    tasks = [limited_process(doc_id) for doc_id in document_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    return results
```

### 6. Resume After Failure

```python
# Resume from last checkpoint
result = await compiled.ainvoke(
    None,  # None = resume from checkpoint
    config={"configurable": {"thread_id": thread_id}}
)
```

### 7. Human-in-the-Loop

```python
from langgraph.types import interrupt

def review_step(state):
    """Pause for human review."""
    # This pauses execution until human provides input
    user_feedback = interrupt(
        "Please review the generated content before continuing"
    )

    return {"reviewed": True, "feedback": user_feedback}

# Resume with Command
from langgraph.types import Command

result = await compiled.ainvoke(
    Command(resume="user approved"),
    config=config
)
```

---

## Database Schema

### workflows (Workflow Definitions)
```sql
CREATE TABLE workflows (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    nodes JSON NOT NULL,      -- Graph nodes with agent configs
    edges JSON NOT NULL,      -- Graph edges
    metadata JSON,            -- Tags, categories, etc.
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### LangGraph Checkpoints (Auto-managed by checkpointer)
These tables are created and managed by LangGraph:
- `checkpoints` - State snapshots at each step
- `checkpoint_writes` - Pending writes
- `checkpoint_metadata` - Thread metadata

We **query** them, we don't create them!

### activities (High-Level Tracking)
```sql
CREATE TABLE activities (
    id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES workflows(id),
    thread_id TEXT NOT NULL,      -- LangGraph thread
    type TEXT NOT NULL,           -- workflow_started, node_completed, etc.
    status TEXT NOT NULL,         -- running, completed, failed
    message TEXT,
    metadata JSON,
    created_at TIMESTAMP
);
```

### schedules (Automation)
```sql
CREATE TABLE schedules (
    id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES workflows(id),
    schedule_type TEXT NOT NULL,  -- cron, interval
    schedule_config JSON NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP
);
```

### triggers (Event-Based Automation)
```sql
CREATE TABLE triggers (
    id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES workflows(id),
    trigger_type TEXT NOT NULL,   -- file_created, file_modified
    trigger_config JSON NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP
);
```

---

## API Endpoints

### Workflow Management
- POST /api/workflows - Create workflow definition
- GET /api/workflows - List workflows
- GET /api/workflows/{id} - Get workflow
- PUT /api/workflows/{id} - Update workflow
- DELETE /api/workflows/{id} - Delete workflow
- POST /api/workflows/import - Import from JSON
- GET /api/workflows/{id}/export - Export to JSON

### Execution (with LangGraph threads)
- POST /api/workflows/{id}/execute - Execute workflow
  - Body: `{document_ids: [...], config: {...}}`
  - Returns: `{threads: [{thread_id, status, ...}]}`
- GET /api/workflows/threads/{thread_id} - Get thread state
- POST /api/workflows/threads/{thread_id}/resume - Resume execution
- POST /api/workflows/threads/{thread_id}/cancel - Cancel execution

### Activities
- GET /api/activities - List activities
- GET /api/activities/{id} - Get activity details
- WS /api/activities/stream - WebSocket for real-time updates

### Comparison
- POST /api/compare - Compare models
  - Body: `{workflow_id, models: [...], document_ids: [...]}`
  - Returns: `{results: [{model, cost, time, output}]}`

### Automation
- POST /api/schedules - Create schedule
- GET /api/schedules - List schedules
- PUT /api/schedules/{id} - Update schedule
- DELETE /api/schedules/{id} - Delete schedule
- POST /api/triggers - Create trigger
- GET /api/triggers - List triggers

### MCP
- GET /api/mcp/servers - List connected MCP servers
- POST /api/mcp/servers - Connect to MCP server
- GET /api/mcp/tools - List available MCP tools

---

## Implementation Phases (REVISED - FASTER!)

### Phase 0: Quick Win (1-2 days)
**TODO-063**: Increase window size

### Phase 1: LangGraph Foundation (2 weeks)
- TODO-064: Configure LangGraph checkpointing (DuckDB)
- TODO-065: Workflow definition persistence (CRUD)
- TODO-066: Execution API with thread management
- TODO-067: Workflow library UI
- TODO-068: Integration testing

### Phase 2: Batch & Activity (2 weeks)
- TODO-069: Batch execution system
- TODO-070: Activity tracking + WebSocket streaming
- TODO-071: Activity monitor UI
- TODO-072: Integration testing

### Phase 3: Agents & MCP (1 week!)
- TODO-073: Agent node support (create_react_agent)
- TODO-074: MCP integration (langchain-mcp-adapters)
- TODO-075: MCP UI
- TODO-076: Integration testing

### Phase 4: Advanced Features (2-3 weeks)
- TODO-077: Multi-agent workflows (supervisor/swarm)
- TODO-078: Model comparison engine
- TODO-079: Comparison UI
- TODO-080: Scheduler (APScheduler)
- TODO-081: File system triggers (watchdog)
- TODO-082: Automation UI
- TODO-083: Action library
- TODO-084: Action library UI

**Total: 7-9 weeks** (down from 10-14 weeks!)

---

## Dependencies to Install

### Python Backend
```bash
# Core LangGraph
pip install langgraph

# Checkpointing
pip install langgraph-checkpoint-postgres
# Or for local dev:
pip install langgraph-checkpoint-sqlite

# Agent support
pip install langgraph-prebuilt  # Included in langgraph
pip install langgraph-supervisor
pip install langgraph-swarm

# MCP integration
pip install langchain-mcp-adapters

# Memory
pip install langmem

# Evaluation (optional)
pip install agentevals

# Automation
pip install apscheduler watchdog

# Existing dependencies
# langchain, langchain-openai, etc. already installed
```

---

## What We DON'T Need to Build

- ❌ Custom job queue (LangGraph threads)
- ❌ Custom checkpoint system (LangGraph checkpointer)
- ❌ Custom pause/resume logic (LangGraph durable execution)
- ❌ Custom MCP client (langchain-mcp-adapters)
- ❌ Custom agent system (create_react_agent)
- ❌ Multi-agent orchestration (langgraph-supervisor/swarm)
- ❌ Manual state tracking (LangGraph handles it)
- ❌ Custom streaming (LangGraph has built-in streaming)

---

## What We DO Build

- ✅ Workflow definition storage (JSON in DuckDB)
- ✅ UI for workflow creation/editing
- ✅ Batch execution wrapper (iterate documents → threads)
- ✅ Activity log (high-level tracking)
- ✅ WebSocket streaming for UI updates
- ✅ Comparison engine (parallel execution across models)
- ✅ Scheduler integration (APScheduler)
- ✅ File trigger system (watchdog)
- ✅ Action library (workflow templates)
- ✅ SwiftUI interfaces for all features

---

## Success Metrics

### Phase 1
- ✅ Workflows persist as definitions
- ✅ LangGraph checkpointing works
- ✅ Can execute with thread IDs
- ✅ Can resume from checkpoint
- ✅ Import/export workflows

### Phase 2
- ✅ Batch execution on 100+ files
- ✅ Real-time progress updates
- ✅ Activity monitor shows all operations
- ✅ Can pause/resume workflows

### Phase 3
- ✅ Agent nodes work in workflows
- ✅ MCP tools load dynamically
- ✅ Multi-agent collaboration works

### Phase 4
- ✅ Model comparison with 5+ models
- ✅ Scheduled workflows execute
- ✅ File triggers work
- ✅ Action library functional

---

## Example: Complete Workflow with Agents

```python
from langgraph.graph import StateGraph
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI
from langchain_mcp_adapters import MCPClient

# 1. Define state
class WorkflowState(TypedDict):
    document_id: str
    transcription: str
    summary: str
    tags: list[str]

# 2. Create agents
transcriber_agent = create_react_agent(
    ChatOpenAI("gpt-4"),
    tools=[whisper_tool]
)

cataloguer_agent = create_react_agent(
    ChatOpenAI("gpt-4o-mini"),
    tools=[tag_generator_tool, metadata_extractor_tool]
)

# 3. Build workflow
graph = StateGraph(WorkflowState)

def transcribe_node(state):
    result = transcriber_agent.invoke({
        "messages": [{"role": "user", "content": f"Transcribe document {state['document_id']}"}]
    })
    return {"transcription": result["messages"][-1]["content"]}

def catalogue_node(state):
    result = cataloguer_agent.invoke({
        "messages": [{"role": "user", "content": f"Catalogue: {state['transcription']}"}]
    })
    # Parse tags from result
    return {"tags": parse_tags(result["messages"][-1]["content"])}

graph.add_node("transcribe", transcribe_node)
graph.add_node("catalogue", catalogue_node)
graph.add_edge("transcribe", "catalogue")

# 4. Compile with checkpointer
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

checkpointer = AsyncPostgresSaver(conn_string)
compiled = graph.compile(checkpointer=checkpointer)

# 5. Execute
result = await compiled.ainvoke(
    {"document_id": "doc123"},
    config={"configurable": {"thread_id": "doc123-transcribe-catalogue"}}
)

# Result: {"document_id": "doc123", "transcription": "...", "tags": [...]}
```

---

## Next Steps

1. **Start with TODO-063** - Window size (quick win)
2. **Prototype LangGraph checkpointing** - Test with DuckDB
3. **Begin Phase 1** - LangGraph integration
4. **Install dependencies**: `pip install langgraph langgraph-supervisor langchain-mcp-adapters`

---

## References

- **LangGraph Docs**: https://langchain-ai.github.io/langgraph/
- **Agents**: https://langchain-ai.github.io/langgraph/agents/overview/
- **Persistence**: https://langchain-ai.github.io/langgraph/concepts/persistence/
- **MCP**: https://langchain-ai.github.io/langgraph/concepts/mcp/
- **Durable Execution**: https://langchain-ai.github.io/langgraph/concepts/durable_execution/
- **Supervisor**: https://pypi.org/project/langgraph-supervisor/
- **Swarm**: https://pypi.org/project/langgraph-swarm/
- **MCP Adapters**: https://github.com/langchain-ai/langchain-mcp-adapters

---

**Status**: Complete architecture leveraging all LangGraph capabilities
**Timeline**: 7-9 weeks (much faster than custom implementation!)
**Confidence**: HIGH - using battle-tested LangGraph components
