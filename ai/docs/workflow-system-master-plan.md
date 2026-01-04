# Fichero Workflow System Enhancement - Master Plan

**Created:** 2026-01-04
**Status:** Planning Phase - Awaiting Review
**Estimated Duration:** 10-14 weeks
**Scope:** Transform Fichero into comprehensive AI workflow orchestration platform

---

## Quick Reference

**Total Tasks**: 26 (TODO-063 through TODO-088)
**Phases**: 5 (Quick Win + 4 major phases)
**Priority**: Start with Phase 0 (window size), then Phase 1 (persistence)

---

## Phase Overview

### Phase 0: Quick Win (1-2 days)
**TODO-063**: Increase default window size
- Fix sidebar being cut off on startup
- Pure SwiftUI, no backend changes
- Immediate user value

### Phase 1: Workflow Persistence (2-3 weeks)
**Goal**: Save, load, import, and export workflows

**Backend** (3 tasks):
- TODO-064: Database schema & Pydantic models
- TODO-065: CRUD API endpoints
- TODO-066: Import/export functionality

**Frontend** (2 tasks):
- TODO-067: Workflow list & management UI
- TODO-068: Integration testing

**Key Deliverables**:
- Workflows persist in DuckDB
- JSON import/export
- UI for saving/loading workflows
- All tests passing

### Phase 2: Batch Execution Engine (3-4 weeks)
**Goal**: Run workflows at scale with progress tracking

**Backend** (5 tasks):
- TODO-069: Execution engine design & job model
- TODO-070: Job queue & state management
- TODO-071: Activity tracking system
- TODO-072: WebSocket streaming for progress
- TODO-073: Parallel execution & optimization

**Frontend** (2 tasks):
- TODO-074: Activity monitor UI
- TODO-075: Integration testing

**Key Deliverables**:
- Execute workflows on 100+ files
- Start/stop/pause/resume functionality
- Real-time progress tracking
- Activity monitor showing all operations
- WebSocket-based live updates

### Phase 3: MCP Tools & Agents (2-3 weeks)
**Goal**: Integrate internal/external MCP tools

**Backend** (3 tasks):
- TODO-076: MCP client integration
- TODO-077: Dynamic tool loading from MCP
- TODO-078: MCP server exposure (Fichero as MCP server)

**Frontend** (2 tasks):
- TODO-079: MCP configuration UI
- TODO-080: Integration testing

**Key Deliverables**:
- Connect to external MCP servers
- Load external tools dynamically
- Expose Fichero operations as MCP tools
- UI for managing MCP connections
- Workflows can use MCP tools

### Phase 4: Advanced Features (3-4 weeks)
**Goal**: Workflow chaining, comparison, automation

**Workflow Chaining** (1 task):
- TODO-081: SubWorkflow tool implementation

**Model Comparison** (2 tasks):
- TODO-082: Comparison engine backend
- TODO-083: Comparison mode UI

**Automation & Scheduling** (3 tasks):
- TODO-084: Scheduler system (cron-like)
- TODO-085: File system triggers
- TODO-086: Automation UI

**Action Library** (2 tasks):
- TODO-087: Action library backend
- TODO-088: Action library UI

**Key Deliverables**:
- Chain workflows together (transcribe → catalogue)
- Compare models side-by-side
- Schedule workflows to run at specific times
- Trigger workflows on file system events
- Reusable action library

---

## Database Schema (New Tables)

### workflows
```sql
CREATE TABLE workflows (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    nodes JSON NOT NULL,
    edges JSON NOT NULL,
    metadata JSON,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### jobs
```sql
CREATE TABLE jobs (
    id UUID PRIMARY KEY,
    workflow_id UUID REFERENCES workflows(id),
    status TEXT NOT NULL,
    total_items INTEGER,
    processed_items INTEGER,
    failed_items INTEGER,
    config JSON,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### job_items
```sql
CREATE TABLE job_items (
    id UUID PRIMARY KEY,
    job_id UUID REFERENCES jobs(id),
    document_id UUID,
    status TEXT NOT NULL,
    result JSON,
    error TEXT,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### activities
```sql
CREATE TABLE activities (
    id UUID PRIMARY KEY,
    type TEXT NOT NULL,
    status TEXT NOT NULL,
    message TEXT,
    metadata JSON,
    parent_id UUID,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### schedules
```sql
CREATE TABLE schedules (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    workflow_id UUID REFERENCES workflows(id),
    schedule_type TEXT NOT NULL,
    schedule_config JSON NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

### triggers
```sql
CREATE TABLE triggers (
    id UUID PRIMARY KEY,
    name TEXT NOT NULL,
    workflow_id UUID REFERENCES workflows(id),
    trigger_type TEXT NOT NULL,
    trigger_config JSON NOT NULL,
    enabled BOOLEAN DEFAULT true,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);
```

---

## New API Endpoints

### Workflows
- POST /api/workflows - Create workflow
- GET /api/workflows - List workflows
- GET /api/workflows/{id} - Get specific workflow
- PUT /api/workflows/{id} - Update workflow
- DELETE /api/workflows/{id} - Delete workflow
- POST /api/workflows/import - Import from JSON
- GET /api/workflows/{id}/export - Export to JSON

### Jobs (Batch Execution)
- POST /api/jobs - Create execution job
- GET /api/jobs - List jobs
- GET /api/jobs/{id} - Get job status
- POST /api/jobs/{id}/start - Start job
- POST /api/jobs/{id}/pause - Pause job
- POST /api/jobs/{id}/resume - Resume job
- POST /api/jobs/{id}/cancel - Cancel job
- GET /api/jobs/{id}/items - Get job items

### Activities
- GET /api/activities - List activities
- GET /api/activities/{id} - Get activity details
- WS /api/activities/stream - WebSocket stream

### Comparison
- POST /api/compare - Compare models

### Automation
- POST /api/schedules - Create schedule
- GET /api/schedules - List schedules
- PUT /api/schedules/{id} - Update schedule
- DELETE /api/schedules/{id} - Delete schedule
- POST /api/triggers - Create trigger
- GET /api/triggers - List triggers
- PUT /api/triggers/{id} - Update trigger
- DELETE /api/triggers/{id} - Delete trigger

### MCP
- GET /api/mcp/servers - List MCP servers
- POST /api/mcp/servers - Add MCP server
- GET /api/mcp/tools - List available tools
- POST /api/mcp/tools/{tool_id}/execute - Execute MCP tool

---

## File Organization

### Backend (Python)
```
src/fichero/
├── workflows/
│   ├── persistence.py      # Database CRUD (NEW)
│   ├── import_export.py    # Import/export logic (NEW)
│   └── batch.py            # Batch execution (NEW)
├── mcp/                    # MCP integration (NEW)
│   ├── client.py
│   ├── server.py
│   └── tools.py
├── automation/             # Scheduling & triggers (NEW)
│   ├── scheduler.py
│   ├── triggers.py
│   └── watchers.py
├── activities/             # Activity tracking (NEW)
│   ├── logger.py
│   ├── models.py
│   └── stream.py
└── api/routes/
    ├── workflows.py        # EXTEND with CRUD
    ├── comparison.py       # NEW
    ├── automation.py       # NEW
    └── activities.py       # NEW
```

### Frontend (Swift)
```
Fichero/Fichero/
├── Views/
│   ├── Sidebar/
│   │   └── CompareMode.swift       # NEW
│   ├── Workflow/
│   │   ├── WorkflowListView.swift  # NEW
│   │   └── ActionLibrary.swift     # NEW
│   ├── Activities/
│   │   └── ActivityMonitor.swift   # NEW
│   └── Automation/
│       └── AutomationView.swift    # NEW
└── Services/
    ├── WorkflowService.swift       # NEW
    ├── ActivityService.swift       # NEW
    └── AutomationService.swift     # NEW
```

---

## Dependencies Between Phases

```
Phase 0 (Window Size)
  ↓ Independent

Phase 1 (Persistence)
  ↓ Independent

Phase 2 (Execution) ← Phase 1
  ↓ Requires saved workflows

Phase 3 (MCP Tools) ← Phase 1
  ↓ Can run in parallel with Phase 2

Phase 4 (Advanced) ← Phases 1, 2, 3
  ├─ Workflow chaining ← Phase 1
  ├─ Comparison ← Phase 2
  ├─ Automation ← Phase 2
  └─ Actions ← Phase 1
```

---

## Testing Strategy

### Unit Tests (Required)
- All new backend modules >= 80% coverage
- Mock external dependencies (database, MCP, filesystem)
- Fast execution (< 1 second per test)

### Integration Tests (Required)
- End-to-end workflow save/load/execute
- Import/export round-trip
- Batch execution with real files
- MCP tool integration
- WebSocket streaming

### Performance Tests (Phase 2+)
- Batch execution with 1000+ items
- Concurrent job execution
- Database query performance
- WebSocket connection stability

---

## Risk Assessment

### High Risk
1. **Batch execution complexity**: Start/stop/resume requires careful state management
   - *Mitigation*: Comprehensive unit tests, state machine diagram

2. **WebSocket stability**: Real-time updates can be fragile
   - *Mitigation*: Reconnection logic, fallback to polling

3. **MCP integration**: External protocol, compatibility issues
   - *Mitigation*: Test with multiple MCP servers, graceful degradation

### Medium Risk
1. **Database migrations**: Schema changes can be tricky
   - *Mitigation*: Migration tools, backup procedures

2. **Concurrency bugs**: Parallel execution can cause races
   - *Mitigation*: Proper async/await, comprehensive tests

---

## Success Metrics

### Phase 1
- ✅ Workflows persist across app restarts
- ✅ Can import/export workflows as JSON
- ✅ All CRUD operations work in UI

### Phase 2
- ✅ Can execute workflow on 100+ files
- ✅ Real-time progress updates
- ✅ Can pause/resume jobs
- ✅ Activity monitor shows all operations

### Phase 3
- ✅ Can connect to external MCP servers
- ✅ External tools work in workflows
- ✅ Fichero accessible as MCP server

### Phase 4
- ✅ Can chain workflows
- ✅ Comparison mode works with 5+ models
- ✅ Can schedule workflows
- ✅ File triggers work
- ✅ Action library has 10+ actions

---

## Implementation Principles

1. **Backend First**: Build and test backend before frontend
2. **Unit Tests Always**: No code without tests
3. **Small PRs**: Each task is a separate commit
4. **Don't Break Things**: All existing features keep working
5. **SwiftUI Only**: No AppKit unless absolutely necessary
6. **Document As You Go**: Update docs with each change

---

## Next Steps

1. **Review this plan** - Confirm scope and approach
2. **Start Phase 0** - Quick win (window size)
3. **Execute Phase 1** - Build persistence layer
4. **Iterate** - Complete each phase before next

---

## Timeline Estimate

- **Phase 0**: 1-2 days (1 task)
- **Phase 1**: 2-3 weeks (5 tasks)
- **Phase 2**: 3-4 weeks (7 tasks)
- **Phase 3**: 2-3 weeks (5 tasks)
- **Phase 4**: 3-4 weeks (8 tasks)

**Total**: 10-14 weeks (26 tasks)

---

## References

- **LangGraph**: https://langchain-ai.github.io/langgraph/
- **MCP Protocol**: https://spec.modelcontextprotocol.io/
- **RAGFlow** (inspiration): https://github.com/infiniflow/ragflow
- **APScheduler**: https://apscheduler.readthedocs.io/
- **Watchdog**: https://python-watchdog.readthedocs.io/
- **FastAPI WebSockets**: https://fastapi.tiangolo.com/advanced/websockets/

---

**Status**: Ready for review and approval to proceed
