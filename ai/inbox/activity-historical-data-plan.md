# Activity Historical Data Plan

## Current Issues

1. **Sidebar empty for non-Global libraries** - `runsForLibrary` returns [] for Catalogue
2. **Historical runs not showing** - need to load from `/api/activity` properly
3. **Runs disappear after completion** - WorkflowExecutionObserver removes after 30s
4. **Console/Progress are too similar** - Console should show actual log messages

## What Backend Already Has

```
activities table:
├── id, type, level, timestamp, message
├── workflow_id, thread_id, node_id
├── metadata (JSON) - workflow_name, node_name
├── duration_ms, error
└── Indexes on timestamp, type, workflow_id
```

**Activity Types Stored:**
- workflow_started, workflow_completed, workflow_failed
- node_started, node_completed, node_failed
- batch events...

## What Backend Needs (for full feature set)

### 1. Workflow Runs Table (new)
Store a summary record for each run:
```python
CREATE TABLE workflow_runs (
    id TEXT PRIMARY KEY,           -- thread_id
    workflow_id TEXT NOT NULL,
    workflow_name TEXT,
    status TEXT,                   -- running, completed, failed, cancelled
    started_at TIMESTAMP,
    completed_at TIMESTAMP,
    duration_ms FLOAT,
    total_files INT,
    processed_files INT,
    error_count INT,
    error TEXT,
    graph_json TEXT,               -- LangGraph structure at run time
    workflow_snapshot TEXT,        -- Workflow definition JSON snapshot
);
```

### 2. Store LangGraph Definition
When building the graph, save the Python code or structure:
```python
# In executor.py when building graph
workflow_runs.insert({
    'graph_json': json.dumps(graph_structure),
    'workflow_snapshot': json.dumps(workflow_definition),
})
```

### 3. API Endpoint for Runs
```python
GET /api/workflow/runs
GET /api/workflow/runs/{run_id}
GET /api/workflow/runs/{run_id}/graph  # Returns LangGraph structure
GET /api/workflow/runs/{run_id}/events  # All activity events for this run
```

## Frontend Changes Needed

### 1. Fix Library Filtering
Activity is global - show for ALL libraries, not just Global:
```swift
// ActivitySidebarContent.swift
private func runsForLibrary(_ library: LibraryManager.LibraryReference) -> [ActivityRun] {
    // Remove the global-only filter
    // guard library.id == LibraryManager.globalLibraryId else { return [] }

    // Show ALL runs under Global library section
    guard library.id == LibraryManager.globalLibraryId else { return [] }
    // ... rest of logic
}
```

Actually, the issue is: user is viewing "Catalogue" library, but runs are global.
**Solution**: Only show Activity under Global library section.

### 2. Hierarchical Sidebar Structure
```
▼ Global
  ▼ New Workflow                    ← Workflow name (grouped)
    ▼ Run Jan 25, 2:28 PM           ← Individual run (expandable)
      ├── Console                   ← Log messages
      ├── Progress                  ← Stats/timing
      └── Errors (1)                ← Error list
    ▶ Run Jan 25, 2:06 PM           ← Older run
    ▶ Run Jan 25, 1:24 PM
  ▼ Other Workflow
    ▶ Run Jan 24, 3:30 PM
```

### 3. Console View Content
Show actual activity log entries:
```swift
// ActivityConsoleView - historical mode
ForEach(activityItems) { item in
    // Show: timestamp | type | message
    // Example: 14:28:00 | node_completed | Node 'describe' completed in 39042ms
}
```

### 4. Progress View Content
Show timing breakdown:
- Workflow duration
- Per-node timing
- Success/failure counts

### 5. Graph View (new child type)
Show LangGraph structure visualization (if stored)

## Implementation Steps

### Phase 1: Fix Frontend (no backend changes)

1. **Fix sidebar to show historical runs**
   - Remove non-Global library filter OR only show Activity section for Global
   - Group runs by workflow name
   - Format: "Workflow Name" → "Run [timestamp]"

2. **Console shows activity log**
   - Load all activity events for thread_id
   - Display as timestamped log entries

3. **Progress shows timing**
   - Calculate from activity events
   - Show node durations

### Phase 2: Backend Enhancements

1. **Create workflow_runs table**
   - Summary record per run
   - Store workflow snapshot

2. **Add /api/workflow/runs endpoints**
   - List all runs with pagination
   - Get run details including all events

3. **Store graph structure**
   - Capture LangGraph definition at build time
   - Enable "Graph" view in frontend

## Questions

1. **Should we group by workflow name?**
   - Yes: Cleaner hierarchy, like Xcode shows by target
   - Format: Workflow Name → Run [timestamp]

2. **How far back to show?**
   - Last 7 days by default
   - Pagination for older runs

3. **What if same workflow runs multiple times?**
   - Group under workflow name
   - Each run shows timestamp

4. **Store raw Python logs?**
   - Complex to implement
   - Activity events give most useful info
   - Could add a "log_output" field to workflow_runs
