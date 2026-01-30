# Activity View Plan

## Goal
Xcode-style Report Navigator for monitoring workflow runs, especially large batches (100K+ items).

## Architecture

```
┌──────────────────────┐     ┌─────────────────────────────────────────────────┐
│ Activity Sidebar     │     │ Activity Detail View                            │
├──────────────────────┤     ├─────────────────────────────────────────────────┤
│ ▼ Global             │     │ ┌───────────────────────────────────────────┐   │
│   ⏵ New Workflow     │ ──► │ │ Stats Bar                                 │   │
│     ▷ Console        │     │ │ ⏵ Running | 45,234/100,000 | ETA: 2h 15m  │   │
│     📊 Progress      │     │ │ ✓ 45,000 | ✗ 234 | ⚠ 12 warnings         │   │
│     ⚠️ Errors (234)  │     │ └───────────────────────────────────────────┘   │
│   ✓ Describe Batch   │     │ ┌───────────────────────────────────────────┐   │
│   ✓ Tag Workflow     │     │ │ Tab Bar: Console | Progress | Errors | Graph │ │
│ ▼ Catalogue          │     │ └───────────────────────────────────────────┘   │
│   (runs...)          │     │ ┌───────────────────────────────────────────┐   │
└──────────────────────┘     │ │ Content (based on tab/selection)          │   │
                             │ │                                           │   │
                             │ │ [Console]                                 │   │
                             │ │ Processing: /images/photo_45234.jpg       │   │
                             │ │ Node: describe_image → Completed (0.3s)   │   │
                             │ │ Node: extract_tags → Running...           │   │
                             │ │                                           │   │
                             │ │ [Progress]                                │   │
                             │ │ ████████████░░░░░░░░ 45% (45,234/100,000) │   │
                             │ │ Rate: 5.2 items/sec                       │   │
                             │ │ Started: 2:30 PM | ETA: 4:45 PM           │   │
                             │ │                                           │   │
                             │ │ [Errors]                                  │   │
                             │ │ ✗ image_1234.jpg: File not found          │   │
                             │ │ ✗ image_5678.jpg: OCR timeout             │   │
                             │ │                                           │   │
                             │ │ [Graph]                                   │   │
                             │ │ LangGraph visualization for debugging     │   │
                             │ └───────────────────────────────────────────┘   │
                             └─────────────────────────────────────────────────┘
```

## Components

### 1. ActivitySidebarContent (update existing)
- **Selection handling**: Click run → update `viewMode` with `SelectedActivityRun`
- **Children**: Console, Progress, Errors as selectable items
- **Live updates**: Spinning icon for running, counts update in real-time
- **Load history**: Fetch from `/api/activity` on appear

### 2. ActivityDetailView (new)
- **Stats bar**: Progress, counts, ETA (always visible)
- **Tab bar**: Console | Progress | Errors | Graph
- **Content area**: Changes based on selected tab

### 3. ConsoleView (new)
- Streaming log output via SSE (`/api/workflow/execute/{thread_id}/stream`)
- Filter: All / Warnings / Errors
- Auto-scroll with pause option
- Copy log to clipboard

### 4. ProgressView (new)
- Progress bar with percentage
- Throughput rate (items/sec)
- Time started, elapsed, ETA
- Current file being processed
- Per-node timing breakdown

### 5. ErrorsView (new)
- Filtered list of errors only
- Group by error type
- Click to see full details
- Retry failed items button

### 6. GraphView (new - optional/debug)
- Render LangGraph structure
- Show current node highlighted
- Node execution times

## Data Flow

### Live Runs (WorkflowExecutionObserver)
```
WorkflowExecutionObserver.activeExecutions[workflowId]
├── id, name, status
├── overallProgress (0.0 - 1.0)
├── currentNodeName
├── processedCount / totalCount
├── errors[]
└── logs[] (streaming via SSE)
```

### Historical Runs (ActivityService)
```
GET /api/activity?types=workflow_completed,workflow_failed&since=7d
├── id, type, level, timestamp
├── workflow_id, thread_id
├── message, error
└── metadata (duration_ms, etc.)
```

### Run Details (on selection)
```
GET /api/activity?workflow_id={id}
├── All activity events for this run
├── Node starts/completions
├── Errors and warnings
└── File processing events
```

## Implementation Steps

1. **Update AppViewMode** ✓
   - `case activity(SelectedActivityRun?)` - done

2. **Update ActivitySidebarContent**
   - Add selection state
   - Make runs clickable → update viewMode
   - Add child items (Console, Progress, Errors)

3. **Create ActivityDetailView**
   - Stats bar component
   - Tab bar for switching views
   - Container for content views

4. **Create ConsoleView**
   - TextEditor for log display
   - SSE connection for streaming
   - Filter controls

5. **Create ProgressView**
   - Progress bar
   - Stats display
   - Current file indicator

6. **Create ErrorsView**
   - Filtered error list
   - Error details on click

7. **Update ContentView**
   - Show ActivityDetailView when activity mode with selection

8. **Backend enhancements** (if needed)
   - Ensure SSE streaming includes file progress
   - Add per-file activity events

## Open Questions

1. Should Console/Progress/Errors be tabs or sidebar children?
   - Tabs = cleaner, like Xcode's filter tabs
   - Children = more discoverable, can show counts

2. LangGraph visualization - priority?
   - Nice for debugging but complex to implement
   - Could be Phase 2

3. Batch vs single workflow distinction?
   - Batches have items with individual status
   - Single workflows have nodes/steps
   - May need different views
