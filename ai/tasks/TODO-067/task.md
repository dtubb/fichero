# TODO-067: Build Workflow Library UI

**Category**: Frontend
**Priority**: P1 (High)
**Dependencies**: TODO-065 (Workflow Persistence), TODO-066 (Execution API)
**Estimated Time**: 2-3 days

---

## Overview

Build SwiftUI views for the workflow library, providing a complete UI for managing and executing saved workflows. This integrates the backend persistence (TODO-065) and execution APIs (TODO-066) with the frontend.

---

## Current State Analysis

### ✅ Already Implemented

1. **Backend Infrastructure**:
   - `/workflows` CRUD endpoints (create, read, update, delete, duplicate)
   - `/workflow-execution` endpoints (execute, resume, status, list threads, delete thread)
   - WorkflowStore backend with full persistence

2. **Swift Services**:
   - `WorkflowStore` (@ObservableObject) with methods:
     - `loadWorkflows()` - fetch from backend
     - `saveWorkflow()`, `updateWorkflow()`, `deleteWorkflow()`
     - `duplicateWorkflow()`, `renameWorkflow()`
     - `importWorkflow()`, `exportWorkflow()`
   - `WorkflowService` - API client wrapping all endpoints

3. **Workflow Editor**:
   - `WorkflowEditor` - visual canvas for editing workflows
   - `WorkflowInspector` - tools palette on the right
   - `WorkflowSidebarItem` - sidebar representation

4. **View Mode Integration**:
   - `SidebarMode.workflows` - sidebar mode for workflows
   - `AppViewMode.workflow(WorkflowSidebarItem?)` - content mode
   - When workflow selected → shows `WorkflowEditor`

### ❌ Missing Implementation

**The workflow library browser view** - What shows in the center pane when:
- Sidebar mode is `.workflows`
- But NO specific workflow is selected (viewMode = `.workflow(nil)`)

Currently shows `WorkflowEditor` with no workflow, but should show a library browser like:
- Document library (icons/list/table views)
- Search results view
- Chat conversation list

---

## Implementation Plan

### Step 1: Create WorkflowLibraryView

**File**: `Fichero/Fichero/Views/Workflow/WorkflowLibraryView.swift`

A view similar to `DocumentBrowserView` that shows:
- List/grid of saved workflows
- Workflow metadata (name, description, node count, last modified)
- Actions: Execute, Edit, Duplicate, Delete, Export
- Empty state when no workflows exist

**Layout Options**:
- List view (default)
- Grid/card view
- Table view with columns

**Features**:
- Search/filter workflows
- Sort by name, date created, last modified
- Select workflow → execute or edit
- Context menu actions (right-click)

### Step 2: Add Execution Controls

**Execution Button** in each workflow card/row:
- Play button icon
- Launches workflow execution
- Shows loading state during execution

**ExecutionStatusView**:
- Shows when workflow is executing
- Displays thread_id, status (running/paused/completed/failed)
- Progress indication
- Results when complete
- Error messages if failed

### Step 3: Integration with Execution API

Use the execution endpoints from TODO-066:
```swift
// Execute workflow
POST /api/workflow-execution/execute
- Body: {workflow_id, inputs, thread_id?, interrupt_before, interrupt_after}
- Returns: {thread_id, status, checkpoint_id, current_state}

// Check status
GET /api/workflow-execution/threads/{thread_id}/status

// Resume paused workflow
POST /api/workflow-execution/threads/{thread_id}/resume

// List all execution threads
GET /api/workflow-execution/threads
```

### Step 4: Execution History/Threads View

**WorkflowThreadsView** (optional enhancement):
- Shows execution history
- List of threads with status
- Ability to resume paused workflows
- View execution results
- Delete old threads

### Step 5: Update ContentView

Modify `ContentView.swift` line ~518 to show WorkflowLibraryView when no workflow selected:

```swift
case .workflow(let workflow):
    if let selectedWorkflow = workflow {
        // Edit mode - show canvas
        WorkflowEditor(
            workflow: selectedWorkflow,
            editingWorkflow: $editingWorkflow,
            displayMode: viewDisplayMode
        )
    } else {
        // Library mode - show browser
        WorkflowLibraryView(
            workflows: workflowStore.workflows,
            onSelect: { workflowItem in
                viewMode = .workflow(workflowItem)
            },
            onExecute: { workflowId in
                // Execute workflow
            }
        )
    }
```

---

## UI Design Patterns

### Workflow Card (Grid View)

```
┌──────────────────────────┐
│ ⚙️ Workflow Name         │
│                          │
│ Description text...      │
│                          │
│ 🔹 5 nodes  📅 2 days ago│
│ ───────────────────────  │
│ ▶️ Execute  ✏️ Edit      │
└──────────────────────────┘
```

### Workflow Row (List View)

```
⚙️ Workflow Name
   Description text...
   🔹 5 nodes • 📅 Last modified 2 days ago
   ▶️ Execute  ✏️ Edit  ⋯ More
```

### Execution Status Overlay

```
┌──────────────────────────┐
│ Executing: My Workflow   │
│ ───────────────────────  │
│ Thread: thread-abc123    │
│ Status: Running...       │
│ Progress: [████████░░] 80%│
│                          │
│ [Pause] [Cancel]         │
└──────────────────────────┘
```

---

## API Integration

### WorkflowStore Extensions

Add execution methods to `WorkflowStore`:

```swift
// Execute a saved workflow
func executeWorkflow(
    _ id: String,
    inputs: [String: Any] = [:],
    interruptBefore: [String] = []
) async throws -> ExecutionStatus {
    // Call execution API
}

// Get execution status
func getExecutionStatus(_ threadId: String) async throws -> ExecutionStatus {
    // Call status API
}

// Resume paused workflow
func resumeWorkflow(_ threadId: String, inputs: [String: Any]? = nil) async throws -> ExecutionStatus {
    // Call resume API
}

// List all threads
func listExecutionThreads(limit: Int = 100) async throws -> [ExecutionThread] {
    // Call list threads API
}
```

### New Models

```swift
struct ExecutionStatus: Codable {
    let threadId: String
    let workflowId: String
    let workflowName: String
    let status: ExecutionStatusType  // running, paused, completed, failed
    let checkpointId: String?
    let currentState: [String: AnyCodable]?
    let error: String?
}

enum ExecutionStatusType: String, Codable {
    case running
    case paused
    case completed
    case failed
}

struct ExecutionThread: Codable, Identifiable {
    var id: String { threadId }
    let threadId: String
    let workflowId: String
    let workflowName: String
    let status: ExecutionStatusType
    let checkpointId: String?
}
```

---

## Files to Create

1. **Views/Workflow/WorkflowLibraryView.swift** (200-300 lines)
   - Main library browser view
   - Grid/list layout switcher
   - Empty state view

2. **Views/Workflow/WorkflowCardView.swift** (100-150 lines)
   - Individual workflow card for grid view
   - Execute/Edit buttons
   - Context menu

3. **Views/Workflow/WorkflowRowView.swift** (80-120 lines)
   - Individual workflow row for list view
   - Compact layout with actions

4. **Views/Workflow/ExecutionStatusView.swift** (150-200 lines)
   - Shows execution progress
   - Pause/resume/cancel controls
   - Results display

5. **Views/Workflow/WorkflowThreadsView.swift** (Optional, 200-250 lines)
   - Execution history browser
   - Thread management

6. **Models/WorkflowExecution.swift** (50-80 lines)
   - ExecutionStatus struct
   - ExecutionThread struct
   - ExecutionStatusType enum

---

## Testing Checklist

### Manual Testing

- [ ] Load workflows from backend on app launch
- [ ] Display workflows in grid view
- [ ] Display workflows in list view
- [ ] Empty state shows when no workflows exist
- [ ] Click Execute → workflow runs successfully
- [ ] Execution status updates in real-time
- [ ] Completed workflows show results
- [ ] Failed workflows show error messages
- [ ] Click Edit → opens workflow in editor
- [ ] Duplicate workflow creates copy
- [ ] Delete workflow removes from list
- [ ] Export workflow saves JSON
- [ ] Import workflow loads from JSON
- [ ] Pause workflow at interrupt point
- [ ] Resume paused workflow continues
- [ ] Execution threads list shows all runs
- [ ] Delete thread removes from history

### Integration Points

- [ ] WorkflowStore loads on app launch
- [ ] Sidebar shows workflows section
- [ ] Selecting workflow switches to library view
- [ ] Creating new workflow adds to list
- [ ] Execution API calls succeed
- [ ] Status updates poll correctly
- [ ] Checkpointing works end-to-end

---

## Success Criteria

- [x] Backend APIs implemented (TODO-065, TODO-066)
- [ ] WorkflowLibraryView shows saved workflows
- [ ] Execute button runs workflows using execution API
- [ ] Status view shows execution progress
- [ ] Results display when workflow completes
- [ ] Error handling for failed executions
- [ ] Pause/resume workflow functionality
- [ ] Execution history/threads view (optional)
- [ ] Import/export workflows from UI

---

## Next Steps After Completion

After TODO-067, the workflow system will have:
- ✅ LangGraph backend with checkpointing
- ✅ Workflow persistence
- ✅ Execution API with threads
- ✅ Comprehensive testing
- ✅ Complete SwiftUI frontend

Then proceed to **Phase 2: Agent Nodes** (TODO-069-072) to add:
- ReAct agents
- Agent configuration UI
- Multi-agent workflows
