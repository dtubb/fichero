# Comprehensive Code Review Plan: TODO-064 to TODO-075

**Date:** 2025-01-08
**Reviewer:** Claude Opus 4.5
**Original Author:** Claude Sonnet

## Objective

Review all code from TODO-064 through TODO-075 to ensure:
1. Backend follows Pydantic/FastAPI best practices
2. Frontend follows SwiftUI-only principles (no AppKit)
3. UI exposes all backend functionality
4. Code compiles (Xcode) and passes SwiftLint
5. No bugs or anti-patterns
6. Proper documentation

---

## Scope Summary

### TODOs Being Reviewed

| TODO | Title | Category | Status |
|------|-------|----------|--------|
| 064 | LangGraph Checkpointing | Backend | Complete |
| 065 | Workflow Definition Persistence | Backend | Complete |
| 066 | Execution API with Thread Management | Backend | Complete |
| 067 | Workflow Library UI | Frontend | NOT STARTED |
| 068 | Integration Testing - Workflow Persistence | Tests | Complete |
| 069 | Agent Node Support | Backend | Complete |
| 070 | Agent Configuration UI | Frontend | NOT STARTED |
| 071 | WorkflowInspector Agents Tab | Frontend | NOT STARTED |
| 072 | Integration Testing - Agent Workflows | Tests | Complete |
| 073 | MCP Manager Backend | Backend | Complete |
| 074 | MCP Tools UI | Frontend | Complete |
| 075 | WorkflowInspector MCP Tools Tab | Frontend | Complete |

### Key Gap Identified

**TODO-067, 070, 071 are NOT IMPLEMENTED** - These are frontend features that should expose backend functionality.

---

## Files to Review

### Backend (Python) - New Files

1. **`src/fichero/workflows/checkpointer.py`** (TODO-064)
   - LangGraph checkpointing with DuckDB
   - Review: Async patterns, error handling, schema design

2. **`src/fichero/workflows/workflow_store.py`** (TODO-065)
   - Workflow CRUD operations
   - Review: Pydantic models, database operations, validation

3. **`src/fichero/api/routes/workflow_execution.py`** (TODO-066)
   - 6 FastAPI endpoints for execution
   - Review: REST conventions, error handling, threading

4. **`src/fichero/workflows/tools/agent.py`** (TODO-069)
   - ReAct agent integration
   - Review: LangGraph patterns, tool binding, state management

5. **`src/fichero/mcp_manager.py`** (TODO-073)
   - MCP server/tool management
   - Review: Transport handling, error recovery, caching

6. **`src/fichero/api/routes/mcp_servers.py`** (TODO-073)
   - MCP CRUD API
   - Review: REST patterns, validation, error codes

7. **`src/fichero/workflows/tools/mcp.py`** (TODO-073)
   - MCP tools for workflows
   - Review: Tool registration, parameter handling

### Backend (Python) - Modified Files

- `src/fichero/models.py` - Workflow model updates
- `src/fichero/api/main.py` - Route registration
- `src/fichero/workflows/types.py` - Type definitions
- `src/fichero/workflows/tools/__init__.py` - Tool exports
- `src/fichero/llm.py` - LLM integration

### Frontend (Swift) - New Files

1. **`Fichero/Fichero/Services/MCPService.swift`** (TODO-074)
   - API client for MCP backend
   - Review: Async/await, error handling, model matching

2. **`Fichero/Fichero/Views/MCPServers/`** (TODO-074)
   - `AddMCPServerSheet.swift` - Server creation form
   - `MCPServerDetailView.swift` - Server details
   - `MCPServersSheet.swift` - Sheet presentation
   - `MCPServersView.swift` - Main list view
   - `MCPToolsCatalogView.swift` - Tool browser
   - Review: SwiftUI patterns, state management, no AppKit

3. **`Fichero/Fichero/Views/Workflow/`** (Various)
   - `WorkflowCanvasView.swift` - Visual editor canvas
   - `WorkflowEditor.swift` - Editor container
   - `WorkflowInspector.swift` - Tool palette (TODO-075)
   - `WorkflowNodeView.swift` - Node rendering
   - `WorkflowEdgeView.swift` - Edge rendering
   - `WorkflowPortView.swift` - Port rendering
   - `NodePopover.swift` - Node configuration
   - `WorkflowOutputLog.swift` - Execution output
   - Review: File sizes, SwiftUI compliance, state patterns

### Frontend (Swift) - Modified Files

- `Fichero/Fichero/Models/Workflow.swift`
- `Fichero/Fichero/Models/WorkflowStore.swift`
- `Fichero/Fichero/Models/WorkflowTypes.swift`
- `Fichero/Fichero/Services/WorkflowService.swift`
- `Fichero/Fichero/Views/ContentView.swift`
- `Fichero/Fichero/Views/Sidebar/SidebarView.swift`
- `Fichero/Fichero/App/AppState.swift`
- `Fichero/Fichero/FicheroApp.swift`

### Integration Tests

- `tests/integration/test_workflow_integration.py` (TODO-068)
- `tests/integration/test_agent_workflow_integration.py` (TODO-072)
- `tests/integration/test_mcp_workflow_integration.py` (TODO-076 - pending)

### Unit Tests

- `tests/unit/test_mcp_manager.py`
- `tests/unit/workflows/`

---

## Review Phases

### Phase 1: Backend Code Review (Agents)

Use parallel agents to review backend files for:
- [ ] Pydantic model correctness (Field, validators, serialization)
- [ ] FastAPI patterns (dependency injection, error handling, status codes)
- [ ] Async/await usage (no blocking in async, proper awaits)
- [ ] Type hints completeness
- [ ] Docstrings for all public functions
- [ ] Error handling (try/except, meaningful messages)
- [ ] Logging (structured, appropriate levels)

**Files:** 7 new + 5 modified

### Phase 2: Frontend Code Review (Agents)

Use parallel agents to review Swift files for:
- [ ] SwiftUI-only (NO AppKit, NSView, NotificationCenter)
- [ ] State management (@StateObject, @ObservedObject, @EnvironmentObject)
- [ ] @MainActor usage (not DispatchQueue.main)
- [ ] Task cancellation (guard !Task.isCancelled)
- [ ] File sizes (< 400 lines)
- [ ] @ViewBuilder on computed views
- [ ] OSLog (not print/NSLog)
- [ ] Proper error handling

**Files:** 12 new + 8 modified

### Phase 3: SwiftLint and Build Verification

- [ ] Run `swiftlint lint --path Fichero/Fichero/`
- [ ] Run `xcodebuild -project Fichero/Fichero.xcodeproj -scheme Fichero -configuration Debug`
- [ ] Document all warnings and errors

### Phase 4: Backend-Frontend Integration Analysis

Verify all backend endpoints have corresponding frontend calls:

| Backend Endpoint | Frontend Call | Status |
|------------------|---------------|--------|
| POST /workflows | WorkflowService.createWorkflow | ? |
| GET /workflows | WorkflowService.listWorkflows | ? |
| GET /workflows/{id} | WorkflowService.getWorkflow | ? |
| PUT /workflows/{id} | WorkflowService.updateWorkflow | ? |
| DELETE /workflows/{id} | WorkflowService.deleteWorkflow | ? |
| POST /workflows/{id}/execute | ? | ? |
| POST /workflows/{id}/pause | ? | ? |
| POST /workflows/{id}/resume | ? | ? |
| GET /workflows/{id}/status | ? | ? |
| GET /mcp-servers | MCPService.listServers | ? |
| POST /mcp-servers | MCPService.createServer | ? |
| GET /mcp-servers/{id} | MCPService.getServer | ? |
| DELETE /mcp-servers/{id} | MCPService.deleteServer | ? |
| POST /mcp-servers/{id}/connect | MCPService.connectServer | ? |
| POST /mcp-servers/{id}/disconnect | MCPService.disconnectServer | ? |
| GET /mcp-servers/{id}/tools | MCPService.getServerTools | ? |
| POST /mcp-servers/{id}/load-tools | MCPService.loadToolsIntoWorkflowRegistry | ? |
| GET /mcp-tools | MCPService.getAllTools | ? |
| POST /mcp-tools/load | MCPService.loadToolsIntoWorkflowRegistry | ? |

### Phase 5: Test Verification

- [ ] Run `PYTHONPATH=src .venv/bin/pytest tests/unit/ --ignore=tests/unit/_archived -v`
- [ ] Run `PYTHONPATH=src .venv/bin/pytest tests/integration/ -v`
- [ ] Document test failures

### Phase 6: Final Report

Create summary document with:
1. Critical bugs found
2. SwiftUI anti-patterns found
3. Backend issues found
4. Missing UI coverage
5. Recommended fixes

---

## Review Criteria Checklist

### Backend (Python)

#### Pydantic
- [ ] All models inherit from BaseModel
- [ ] Field() used for defaults and validation
- [ ] model_config for serialization settings
- [ ] CodingKeys equivalent (alias) where needed
- [ ] Proper Optional[] typing

#### FastAPI
- [ ] Proper HTTP status codes (200, 201, 400, 404, 500)
- [ ] Depends() for dependency injection
- [ ] HTTPException with meaningful detail
- [ ] Proper request/response models
- [ ] Docstrings on all endpoints

#### Async
- [ ] async def for I/O operations
- [ ] await on all async calls
- [ ] No blocking I/O in async functions
- [ ] Proper exception handling in async context

### Frontend (Swift)

#### SwiftUI Compliance (from SWIFTUI_PRINCIPLES.md)
- [ ] NO AppKit (NSView, NSColor, NSFont, etc.)
- [ ] NO NotificationCenter for app logic
- [ ] NO DispatchQueue.main (use @MainActor)
- [ ] NO creating services in view body

#### State Management
- [ ] @StateObject for owned state
- [ ] @ObservedObject for passed state
- [ ] @EnvironmentObject for injected services
- [ ] @State for local view state
- [ ] @Binding for two-way bindings

#### Concurrency
- [ ] @MainActor on UI classes
- [ ] Task { @MainActor in } for UI updates from background
- [ ] guard !Task.isCancelled in .task blocks
- [ ] Sendable conformance where needed

#### Code Quality
- [ ] Files < 400 lines
- [ ] Functions < 50 lines
- [ ] OSLog not print/NSLog
- [ ] @ViewBuilder on computed views
- [ ] Descriptive variable names

---

## Execution Strategy

Given the scope (20+ files), I'll use parallel agents:

1. **Agent 1**: Backend checkpointer + workflow_store
2. **Agent 2**: Backend workflow_execution + agent tools
3. **Agent 3**: Backend MCP manager + routes
4. **Agent 4**: Frontend MCPService + MCP views
5. **Agent 5**: Frontend Workflow views (large files)
6. **Agent 6**: SwiftLint + Xcode build
7. **Agent 7**: Integration coverage analysis

After agents complete, I'll consolidate findings into a single report.

---

## Success Criteria

1. **Zero SwiftLint errors** (warnings acceptable with justification)
2. **Xcode build succeeds** with zero errors
3. **All backend tests pass**
4. **No AppKit usage** in new Swift code
5. **All backend endpoints** have frontend coverage (or documented gaps)
6. **No critical bugs** (data loss, crashes, security issues)
