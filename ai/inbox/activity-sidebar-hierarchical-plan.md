# Activity Sidebar Hierarchical Plan

## Current State
- Flat list of runs (no hierarchy)
- Historical data not loading/showing
- Clicking run → shows detail view (tabs in main area)

## Desired State (Xcode Report Navigator style)

### Wireframe
```
┌──────────────────────────────────┐
│ [Mode Icons]                     │
├──────────────────────────────────┤
│ ▼ Global                         │  ← Library header
│   ▼ ⏵ Describe Batch             │  ← Run (expandable, currently running)
│     │   Today, 2:06 PM           │
│     ├── ▷ Console                │  ← Child: click → shows console in main
│     ├── 📊 Progress              │  ← Child: click → shows progress in main
│     └── ⚠️ Errors (3)            │  ← Child: click → shows errors in main
│   ▶ ✓ Tag Workflow               │  ← Run (collapsed, completed)
│     │   Today, 10:04 AM          │
│   ▶ ✗ OCR Batch                  │  ← Run (collapsed, failed)
│     │   Yesterday, 3:30 PM       │
│ ▼ Catalogue                      │  ← Another library
│   ▶ ✓ Import Run                 │
│     │   Jan 20, 2026             │
└──────────────────────────────────┘
```

### Sidebar Item Structure
```
Library Header
└── Run Item (expandable)
    ├── Name + status icon (⏵ running, ✓ completed, ✗ failed)
    ├── Timestamp (relative or absolute)
    └── Children:
        ├── Console (shows log output)
        ├── Progress (shows progress stats)
        └── Errors (badge count if > 0)
```

### Selection Behavior
| Click On | Main View Shows |
|----------|-----------------|
| Run (parent) | Overview/summary of run |
| Console | Streaming console output |
| Progress | Progress bars, file counts, ETA |
| Errors | Error list with details |

## Issues to Fix

### 1. Historical Data Not Loading
**Current code** (ActivitySidebarContent.swift):
```swift
.task {
    await loadHistoricalRuns()
}
```

**Problem**: May be failing silently. Need to check:
- Is API returning data?
- Is ActivityService.queryActivities working?
- Are we handling the response correctly?

**Debug steps**:
1. Add logging to loadHistoricalRuns
2. Check backend /api/activity endpoint
3. Verify ActivityItem parsing

### 2. Convert Flat List to Hierarchical

**Current**: `List { ForEach(runs) { ActivityRunRow(run: run) } }`

**Needed**: Nested DisclosureGroups or OutlineGroup:
```swift
List {
    ForEach(libraryManager.openLibraries) { library in
        Section {
            ForEach(runsForLibrary(library)) { run in
                DisclosureGroup {
                    // Children
                    ActivityChildRow(type: .console, run: run)
                    ActivityChildRow(type: .progress, run: run)
                    ActivityChildRow(type: .errors, run: run, count: run.errorCount)
                } label: {
                    ActivityRunRow(run: run)
                }
            }
        } header: {
            LibrarySectionHeader(library: library)
        }
    }
}
```

### 3. Selection State

**Need to track**:
- Selected run ID
- Selected child type (console/progress/errors, or nil for overview)

**New selection model**:
```swift
struct ActivitySelection: Equatable {
    let runId: String
    let childType: ActivityChildType?  // nil = run overview

    enum ActivityChildType {
        case console
        case progress
        case errors
    }
}
```

**Update AppViewMode**:
```swift
case activity(ActivitySelection?)
```

## Implementation Steps

### Step 1: Debug Historical Data
- [ ] Add logging to loadHistoricalRuns
- [ ] Test /api/activity endpoint with curl
- [ ] Verify backend is running and returning data

### Step 2: Create Hierarchical Model
- [ ] Create ActivityChildType enum
- [ ] Update ActivitySelection (or create new type)
- [ ] Update AppViewMode if needed

### Step 3: Update ActivitySidebarContent
- [ ] Replace flat list with DisclosureGroup structure
- [ ] Add expansion state tracking (@State var expandedRuns: Set<String>)
- [ ] Create ActivityRunDisclosure view
- [ ] Create ActivityChildRow view

### Step 4: Update Selection Handling
- [ ] Track both run and child selection
- [ ] Update viewMode when selecting run or child
- [ ] Highlight selected item in sidebar

### Step 5: Update ActivityDetailView
- [ ] Handle child type selection
- [ ] Show appropriate content based on selection:
  - Run selected (no child) → Overview tab
  - Console child → Console content
  - Progress child → Progress content
  - Errors child → Errors content

### Step 6: Test
- [ ] Live running workflow shows in sidebar
- [ ] Historical runs load and display
- [ ] Expanding/collapsing works
- [ ] Clicking children updates main view
- [ ] Error badges show correct counts

## Questions

1. **Should children be always visible or only when expanded?**
   - Xcode shows them only when expanded
   - Recommendation: Same as Xcode (DisclosureGroup)

2. **What if a run has no errors?**
   - Still show "Errors" child but no badge
   - Or hide it entirely when count = 0?
   - Recommendation: Always show, no badge when 0

3. **Auto-expand running workflows?**
   - Xcode auto-expands the current run
   - Recommendation: Yes, auto-expand isLive runs

4. **Persist expansion state?**
   - Should we remember which runs are expanded across sessions?
   - Recommendation: No, just expand live runs by default
