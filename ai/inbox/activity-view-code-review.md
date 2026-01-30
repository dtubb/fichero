# Activity View - Systematic Code Review Plan

## Overview
Review all Activity-related code across frontend (Swift) and backend (Python) to ensure consistency, fix bugs, and identify improvements.

---

## Backend (Python) Files to Review

### 1. `src/fichero/api/routes/activity.py`
- [ ] Activity API endpoints (query, recent, stats, stream)
- [ ] ActivityResponse model matches Swift ActivityItem
- [ ] Activity filtering logic
- [ ] SSE streaming endpoints

### 2. `src/fichero/api/routes/workflow_execution.py`
- [ ] SSE event types sent (start, node_begin, node_end, log, complete, error, etc.)
- [ ] Activity tracking calls (workflow_started, workflow_completed, workflow_failed)
- [ ] WorkflowRunResponse model
- [ ] Execution log streaming via SSE "log" events
- [ ] workflow_runs table operations (save/update)

### 3. `src/fichero/workflows/activity.py`
- [ ] ActivityType enum - all types used consistently
- [ ] ActivityTracker class - log methods
- [ ] ActivityStore - query/save methods
- [ ] workflow_runs table schema and methods

---

## Frontend (Swift) Files to Review

### 1. `Fichero/Services/ActivityService.swift`
- [ ] API endpoints match backend routes
- [ ] ActivityItem struct matches ActivityResponse
- [ ] WorkflowRunResponse struct matches backend
- [ ] AnyValueAsString helper for metadata decoding
- [ ] All query methods work correctly

### 2. `Fichero/Services/WorkflowStreamService.swift`
- [ ] WorkflowStreamEvent enum has all cases matching backend SSE events
- [ ] SSE parsing handles all event types
- [ ] Error handling for malformed events

### 3. `Fichero/Services/WorkflowExecutionObserver.swift`
- [ ] WorkflowExecution struct has all needed fields (including logLines)
- [ ] All WorkflowStreamEvent cases handled
- [ ] Completed executions cleaned up properly
- [ ] isRunning flag updated correctly

### 4. `Fichero/Views/Sidebar/Modes/ActivitySidebarContent.swift`
- [ ] Historical runs loading works
- [ ] Live runs display correctly
- [ ] Status mapping from execution to ActivityRunStatus
- [ ] isLive determined correctly
- [ ] Auto-refresh when workflows complete
- [ ] Grouping by workflow name works

### 5. `Fichero/Views/Activity/ActivityDetailView.swift`
- [ ] All ActivityChildType cases have views (.console, .progress, .errors, .graph, .code, .diagram, .log)
- [ ] ActivityConsoleView shows activity items correctly
- [ ] ActivityProgressView shows progress
- [ ] ActivityErrorsView shows errors
- [ ] ActivityGraphView shows checkpoints
- [ ] ActivityCodeView shows Python code
- [ ] ActivityDiagramView shows workflow diagram
- [ ] ActivityLogView streams logs for live runs, shows saved log for completed

### 6. `Fichero/Models/SidebarItem.swift`
- [ ] ActivityChildType enum complete and correct
- [ ] SelectedActivityRun struct has all needed fields
- [ ] AppViewMode.activity case handles selection correctly

### 7. `Fichero/Models/LibraryManager.swift`
- [ ] activityService property exists and initialized correctly

---

## Data Flow to Verify

1. **Workflow Starts**
   - Backend: Creates execution, sends SSE "start" event
   - Frontend: Observer creates WorkflowExecution in activeExecutions
   - Sidebar: Shows live run with spinner

2. **During Execution**
   - Backend: Sends node_begin, node_end, file_start, file_complete, log events
   - Frontend: Observer updates nodeStates, logLines
   - Sidebar: Shows progress, current step
   - Detail views: Console shows events, Log shows streamed lines

3. **Workflow Completes**
   - Backend: Sends "complete" event, saves activity record, saves workflow_run
   - Frontend: Observer sets isRunning=false, status=completed, schedules cleanup
   - Sidebar: Shows checkmark, then after 2s removes from active, reloads history

4. **Viewing History**
   - Backend: /activity endpoint returns completed workflow activities
   - Frontend: loadHistoricalRuns() fetches and stores in historicalRunsByLibrary
   - Sidebar: Shows historical runs under workflow names
   - Detail: Loads saved execution_log and python_code from workflow_run

---

## Known Issues Fixed This Session

1. ✅ ActivityServiceGenerated deleted - replaced with ActivityService
2. ✅ metadata decoding error - added AnyValueAsString wrapper
3. ✅ isLive always true - now checks execution.isRunning
4. ✅ Status always .running - now maps from execution.status
5. ✅ Completed executions not removed - added 2-second delayed cleanup
6. ✅ History not refreshing - added refresh when activeExecutions count decreases
7. ✅ Log view duplicated Console - now streams actual log lines via SSE

---

## Potential Issues to Investigate

1. Library path handling - activities saved to correct library?
2. Thread ID consistency between SSE events and activity records
3. Checkpoint history in Graph view - is it loading correctly?
4. Error handling in all async operations
5. Memory leaks in observers/tasks
6. Race conditions in concurrent execution handling
