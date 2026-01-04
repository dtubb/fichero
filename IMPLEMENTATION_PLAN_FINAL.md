# Fichero Workflow System - Implementation Plan (FINAL)

**Date**: January 4, 2026
**Status**: Complete plan based on existing architecture

---

## What We're Building

**Fichero = Visual LangGraph Editor for macOS**

Users build workflows visually → we convert to LangGraph → LangGraph handles execution, agents, MCP, checkpointing.

---

## Extending Existing UI Structure

### App Menu (Already exists for Models/Providers)
**Add parallel menus for:**

1. **MCP Servers** (like Models menu)
   - Connect to MCP servers
   - Enable/disable servers
   - View available tools

2. **Agents** (like Providers menu)
   - Configure default agents
   - Agent templates
   - Memory settings

### Workflow Inspector (Already exists - right panel)
**Current structure**: Shows tools in `DisclosureGroup` sections

**Add new sections**:
```swift
// Current
DisclosureGroup("Tools") {
    // Built-in tools from backend
}

// Add:
DisclosureGroup("Agents") {
    // Agent types: ReAct, Supervisor, Swarm
}

DisclosureGroup("MCP Tools") {
    // Tools from connected MCP servers
}

DisclosureGroup("Actions") {
    // Saved workflow templates/actions
}
```

**Or use Tabs**:
```swift
TabView {
    ToolsTab()      // Existing
    AgentsTab()     // New
    MCPTab()        // New
    ActionsTab()    // New
}
```

### New View Folders (Following AIProviders pattern)

```
/Views/
├── AIProviders/          # Existing - Provider management
│   ├── ProvidersView.swift
│   ├── AddProviderSheet.swift
│   └── AIModelCatalog.swift
├── MCPTools/             # NEW - MCP management
│   ├── MCPServersView.swift
│   ├── AddMCPServerSheet.swift
│   └── MCPToolCatalog.swift
├── Agents/               # NEW - Agent management
│   ├── AgentsView.swift
│   ├── AddAgentSheet.swift
│   └── AgentTemplates.swift
└── Automation/           # NEW - Scheduling/triggers
    ├── AutomationView.swift
    ├── SchedulesView.swift
    └── TriggersView.swift
```

---

## New Features to Add

### 1. MCP Integration

**Backend** (`src/fichero/mcp/`):
```python
from langchain_mcp_adapters import MCPClient

class MCPManager:
    """Manage MCP server connections."""

    async def connect_server(self, config):
        """Connect to MCP server and load tools."""
        async with MCPClient(config["command"]) as client:
            tools = await client.list_tools()
            # Register tools in workflow registry

    async def list_servers(self):
        """List connected MCP servers."""

    async def list_tools(self, server_id):
        """List tools from specific server."""
```

**Frontend** (`Views/MCPTools/MCPServersView.swift`):
```swift
struct MCPServersView: View {
    @State private var servers: [MCPServer] = []

    var body: some View {
        List(servers) { server in
            HStack {
                Image(systemName: "cube.box")
                Text(server.name)
                Spacer()
                Circle()
                    .fill(server.isConnected ? .green : .gray)
                    .frame(width: 8, height: 8)
            }
        }
        .toolbar {
            Button("Add Server") {
                // Show add server sheet
            }
        }
    }
}
```

**API Endpoints**:
- POST /api/mcp/servers - Connect to MCP server
- GET /api/mcp/servers - List servers
- GET /api/mcp/servers/{id}/tools - List tools
- DELETE /api/mcp/servers/{id} - Disconnect

### 2. Agent Nodes

**Backend** (`src/fichero/workflows/agents.py`):
```python
from langgraph.prebuilt import create_react_agent
from langchain_openai import ChatOpenAI

def create_agent_node(agent_config):
    """Create LangGraph agent node from config."""
    model = ChatOpenAI(model=agent_config["model"])
    tools = load_tools(agent_config["tools"])

    agent = create_react_agent(
        model,
        tools=tools,
        state_modifier=agent_config.get("system_prompt")
    )

    return agent
```

**Frontend** (`Views/Agents/AgentNodeEditor.swift`):
```swift
struct AgentNodeEditor: View {
    @Binding var agentConfig: AgentConfig

    var body: some View {
        Form {
            Picker("Agent Type", selection: $agentConfig.type) {
                Text("ReAct").tag(AgentType.react)
                Text("Supervisor").tag(AgentType.supervisor)
                Text("Swarm").tag(AgentType.swarm)
            }

            Picker("Model", selection: $agentConfig.model) {
                // Model list from providers
            }

            Section("Tools") {
                MultiSelector(
                    "Available Tools",
                    items: availableTools,
                    selected: $agentConfig.tools
                )
            }

            Section("System Prompt") {
                TextEditor(text: $agentConfig.systemPrompt)
                    .frame(minHeight: 100)
            }
        }
    }
}
```

### 3. Automation (Hazel-like)

**Backend** (`src/fichero/automation/`):
```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AutomationManager:
    """Manage scheduled workflows and file triggers."""

    def schedule_workflow(self, workflow_id, cron_expr):
        """Schedule workflow to run on cron schedule."""
        scheduler.add_job(
            execute_workflow,
            'cron',
            args=[workflow_id],
            **parse_cron(cron_expr)
        )

    def watch_folder(self, path, workflow_id, filters):
        """Watch folder and trigger workflow on file events."""
        handler = WorkflowTriggerHandler(workflow_id, filters)
        observer.schedule(handler, path, recursive=True)
```

**Frontend** (`Views/Automation/AutomationView.swift`):
```swift
struct AutomationView: View {
    @State private var schedules: [Schedule] = []
    @State private var triggers: [Trigger] = []

    var body: some View {
        VSplitView {
            // Schedules
            Section("Scheduled Workflows") {
                List(schedules) { schedule in
                    ScheduleRow(schedule: schedule)
                }
                .toolbar {
                    Button("Add Schedule") {
                        // Show schedule editor
                    }
                }
            }

            // Triggers
            Section("Folder Triggers") {
                List(triggers) { trigger in
                    TriggerRow(trigger: trigger)
                }
                .toolbar {
                    Button("Add Trigger") {
                        // Show trigger editor
                    }
                }
            }
        }
    }
}

struct ScheduleEditor: View {
    @Binding var schedule: Schedule

    var body: some View {
        Form {
            Picker("Workflow", selection: $schedule.workflowId) {
                // List of workflows
            }

            Picker("Frequency", selection: $schedule.frequency) {
                Text("Hourly").tag(Frequency.hourly)
                Text("Daily").tag(Frequency.daily)
                Text("Weekly").tag(Frequency.weekly)
                Text("Cron Expression").tag(Frequency.cron)
            }

            if schedule.frequency == .cron {
                TextField("Cron Expression", text: $schedule.cronExpr)
            }
        }
    }
}

struct TriggerEditor: View {
    @Binding var trigger: Trigger

    var body: some View {
        Form {
            Picker("Workflow", selection: $trigger.workflowId) {
                // List of workflows
            }

            Picker("Watch Folder", selection: $trigger.folderPath) {
                // Folder picker
            }

            Picker("Event Type", selection: $trigger.eventType) {
                Text("File Created").tag(EventType.created)
                Text("File Modified").tag(EventType.modified)
                Text("File Deleted").tag(EventType.deleted)
            }

            TextField("File Pattern (e.g., *.pdf)", text: $trigger.pattern)
        }
    }
}
```

### 4. Action Library

**Backend** (`src/fichero/workflows/actions.py`):
```python
class ActionLibrary:
    """Manage reusable workflow actions (single-node workflows)."""

    async def save_action(self, name, node_config):
        """Save a workflow node as a reusable action."""
        action = {
            "name": name,
            "node": node_config,
            "category": detect_category(node_config)
        }
        await db.insert("actions", action)

    async def list_actions(self, category=None):
        """List available actions."""
        if category:
            return await db.query("SELECT * FROM actions WHERE category = ?", category)
        return await db.query("SELECT * FROM actions")
```

**Frontend** (`Views/Workflow/ActionLibrary.swift`):
```swift
struct ActionLibrary: View {
    @State private var actions: [Action] = []
    @State private var selectedCategory: ActionCategory?

    var body: some View {
        HStack(spacing: 0) {
            // Categories
            List(ActionCategory.allCases, selection: $selectedCategory) { category in
                Label(category.name, systemImage: category.icon)
            }
            .frame(width: 150)

            // Actions in category
            ScrollView {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 120))]) {
                    ForEach(filteredActions) { action in
                        ActionCard(action: action)
                            .onDrag {
                                // Drag action to canvas
                                NSItemProvider(object: action)
                            }
                    }
                }
                .padding()
            }
        }
    }

    var filteredActions: [Action] {
        if let category = selectedCategory {
            return actions.filter { $0.category == category }
        }
        return actions
    }
}

struct ActionCard: View {
    let action: Action

    var body: some View {
        VStack {
            Image(systemName: action.icon)
                .font(.title)
            Text(action.name)
                .font(.caption)
        }
        .frame(width: 100, height: 100)
        .background(Color(.controlBackgroundColor))
        .cornerRadius(8)
    }
}
```

---

## Updated File Structure

### Backend
```
src/fichero/
├── workflows/
│   ├── builder.py              # EXISTING
│   ├── executor.py             # EXISTING
│   ├── registry.py             # EXISTING
│   ├── persistence.py          # NEW - workflow CRUD
│   ├── checkpointer.py         # NEW - DuckDB checkpointer
│   ├── agents.py               # NEW - agent node creation
│   └── actions.py              # NEW - action library
├── mcp/                        # NEW
│   ├── __init__.py
│   ├── manager.py              # MCP connection management
│   └── tools.py                # MCP tool adapters
├── automation/                 # NEW
│   ├── __init__.py
│   ├── scheduler.py            # APScheduler integration
│   ├── triggers.py             # File watchers
│   └── integrations.py         # Devon Think, Bookends, etc.
└── api/routes/
    ├── workflows.py            # EXTEND
    ├── execution.py            # NEW
    ├── mcp.py                  # NEW
    ├── agents.py               # NEW
    └── automation.py           # NEW
```

### Frontend
```
Fichero/Fichero/Views/
├── AIProviders/                # EXISTING
├── Workflow/                   # EXISTING
│   ├── WorkflowInspector.swift   # EXTEND - add tabs/sections
│   ├── AgentNodeView.swift       # NEW
│   └── ActionLibrary.swift       # NEW
├── MCPTools/                   # NEW
│   ├── MCPServersView.swift
│   ├── AddMCPServerSheet.swift
│   └── MCPToolCatalog.swift
├── Agents/                     # NEW
│   ├── AgentsView.swift
│   ├── AgentNodeEditor.swift
│   └── AgentTemplates.swift
└── Automation/                 # NEW
    ├── AutomationView.swift
    ├── ScheduleEditor.swift
    └── TriggerEditor.swift
```

---

## Implementation Phases (REVISED AGAIN)

### Phase 0: Quick Win (1 day)
**TODO-063**: Increase window size

### Phase 1: LangGraph Foundation (2 weeks)
- TODO-064: DuckDB checkpointer adapter
- TODO-065: Workflow definition persistence
- TODO-066: Execution API with threads
- TODO-067: Workflow list UI
- TODO-068: Integration tests

### Phase 2: Agents (1 week)
- TODO-069: Agent node support (create_react_agent)
- TODO-070: Agent configuration UI (`Views/Agents/`)
- TODO-071: Update WorkflowInspector with Agents tab
- TODO-072: Integration tests

### Phase 3: MCP Integration (1 week)
- TODO-073: MCP manager backend (langchain-mcp-adapters)
- TODO-074: MCP UI (`Views/MCPTools/`)
- TODO-075: Update WorkflowInspector with MCP tools tab
- TODO-076: Integration tests

### Phase 4: Batch Execution & Monitoring (2 weeks)
- TODO-077: Batch execution system
- TODO-078: Activity tracking + WebSocket
- TODO-079: Activity monitor UI
- TODO-080: Integration tests

### Phase 5: Automation (2 weeks)
- TODO-081: Scheduler (APScheduler)
- TODO-082: File triggers (watchdog)
- TODO-083: App integrations (Devon Think, Bookends, etc.)
- TODO-084: Automation UI (`Views/Automation/`)
- TODO-085: Integration tests

### Phase 6: Action Library (1 week)
- TODO-086: Action library backend
- TODO-087: Action library UI
- TODO-088: Integration tests

### Phase 7: Advanced Features (2 weeks)
- TODO-089: Multi-agent workflows (supervisor/swarm)
- TODO-090: Model comparison engine
- TODO-091: Comparison UI
- TODO-092: Integration tests

**Total: 11-12 weeks**

---

## Database Schema (Additions)

### actions
```sql
CREATE TABLE actions (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    category TEXT NOT NULL,
    node_config JSON NOT NULL,  -- Single node configuration
    icon TEXT,
    created_at TIMESTAMP
);
```

### mcp_servers
```sql
CREATE TABLE mcp_servers (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    command TEXT NOT NULL,      -- e.g., "npx -y @modelcontextprotocol/server-filesystem"
    enabled BOOLEAN DEFAULT true,
    auto_connect BOOLEAN DEFAULT true,
    created_at TIMESTAMP
);
```

### schedules
```sql
CREATE TABLE schedules (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    workflow_id UUID REFERENCES workflows(id),
    frequency TEXT NOT NULL,    -- hourly, daily, weekly, cron
    cron_expr TEXT,             -- If frequency=cron
    enabled BOOLEAN DEFAULT true,
    last_run TIMESTAMP,
    next_run TIMESTAMP,
    created_at TIMESTAMP
);
```

### triggers
```sql
CREATE TABLE triggers (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    workflow_id UUID REFERENCES workflows(id),
    trigger_type TEXT NOT NULL,  -- file_created, file_modified, file_deleted
    folder_path TEXT NOT NULL,
    file_pattern TEXT,           -- e.g., "*.pdf"
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP
);
```

---

## API Endpoints (Additions)

### MCP
- POST /api/mcp/servers
- GET /api/mcp/servers
- GET /api/mcp/servers/{id}/tools
- DELETE /api/mcp/servers/{id}

### Agents
- GET /api/agents/templates
- POST /api/agents/validate

### Automation
- POST /api/schedules
- GET /api/schedules
- PUT /api/schedules/{id}
- DELETE /api/schedules/{id}
- POST /api/schedules/{id}/run
- POST /api/triggers
- GET /api/triggers
- PUT /api/triggers/{id}
- DELETE /api/triggers/{id}

### Actions
- POST /api/actions
- GET /api/actions
- GET /api/actions/categories
- DELETE /api/actions/{id}

---

## Key Integrations

### Devon Think
```python
# Watch Devon Think inbox
trigger = {
    "workflow_id": "process-research-paper",
    "folder_path": "~/Library/Application Support/DEVONthink 3/Inbox",
    "file_pattern": "*.pdf"
}
```

### Bookends
```python
# Use bookends-mcp for bibliography integration
from langchain_mcp_adapters import MCPClient

async with MCPClient("python", "/Users/dtubb/code/bookends-mcp/server.py") as client:
    tools = await client.list_tools()
    # Add to workflow
```

### Calendar Events
```python
# Schedule workflow based on calendar
schedule = {
    "workflow_id": "weekly-summary",
    "frequency": "weekly",
    "day": "sunday",
    "time": "18:00"
}
```

---

## Next Steps

1. **Review this plan** - Confirm approach
2. **Start Phase 0** - Window size fix
3. **Prototype checkpointing** - Test LangGraph with DuckDB
4. **Begin Phase 1** - LangGraph integration

**Ready to start with TODO-063?**

---

## References

- **ai-watcher**: /Users/dtubb/code/ai-watcher
- **bookends-mcp**: /Users/dtubb/code/bookends-mcp
- **LangGraph**: https://langchain-ai.github.io/langgraph/
- **Hazel** (inspiration): https://www.noodlesoft.com/

---

**Status**: Complete implementation plan
**Confidence**: HIGH - leveraging existing patterns and LangGraph
