# Context: Contextual Batch Triggering

## Problem
Batches represent workflow execution on multiple documents, but there's no clear UI to create them. The Batches sidebar exists for monitoring, but users need a way to initiate batch operations.

## User Discussion
> User: "You also said I can't add batches because they're applied to multiple folders. Okay. You certain. Maybe I want to add batches as its own user interface. thoughts?"
>
> AI: "Batches are created when you run a workflow on multiple documents. You don't need a 'New Batch' button."
>
> User: "please make a plan to do each, I think a batch creation UI is a good idea. otherwise how do I trigger a batch? or do I do that from contextual menus and a menu item, and a button button. I'm fine with that. maybe we don't need a batch creation UI. help me think."

## Decision: Contextual Triggering (Not Explicit UI)

### Why Contextual Is Better
1. **Natural workflow**: Select docs → Run workflow (implicit batch)
2. **Less ceremony**: No extra "Create Batch" dialog
3. **Discoverable**: Context menus are standard pattern
4. **Flexible**: Multiple entry points (browser, workflow editor, menu)

### Why Explicit UI Is Worse
1. **Extra step**: Select workflow → Select docs → Configure → Run
2. **Heavyweight**: Feels like filling out a form
3. **Disconnect**: Batch creation separated from document selection
4. **Redundant**: Toolbar/menu already provide creation

## How Other Apps Handle Bulk Operations

### Finder
- Select files → Right-click → "Quick Actions" submenu
- No "Create Batch Operation" UI - just direct actions

### Photos
- Select photos → Click "Edit" or "Share" → Batch applied
- Progress shown in status bar

### Mail
- Select emails → Click "Move" or "Delete" → Batch executed
- No batch creation dialog

### Adobe Lightroom
- Select photos → Menu → "Edit" → Action
- Batch operations are contextual, not explicit entities

**Pattern**: Batches are implementation details, not user-facing objects to "create."

## Batch Mental Model

### What Users Think
"I want to run this workflow on these documents."

### What System Does
1. Create batch object (ID, name, status, progress)
2. Execute workflow on each document
3. Track progress in batch
4. Show results when complete

### What Users See
- Progress bar or status in Batches sidebar
- Notifications when complete/failed
- Results accessible by clicking batch

**User never thinks "I'm creating a batch" - they think "I'm running a workflow."**

## Entry Points Design

### 1. Document Browser (Primary)
Most common workflow:
- User browses/searches documents
- Selects multiple (⌘-click, ⇧-click)
- Right-click → "Run Workflow..."
- Picks workflow
- Batch starts

**Context**: Already looking at documents, wants to process them

### 2. Workflow Editor (Secondary)
Workflow-first approach:
- User opens workflow
- Clicks "Run on Documents..."
- Picks documents
- Batch starts

**Context**: Already looking at workflow, wants to test/apply it

### 3. Menu Bar (Keyboard Users)
For power users:
- Select documents
- Data menu → "Run Workflow on Selection..." (⌘⇧R)
- Picks workflow
- Batch starts

**Context**: Keyboard-driven workflow, no mouse

## Implementation Patterns

### Workflow Picker Sheet
Reusable component:
```swift
struct WorkflowPickerSheet: View {
    let selectedDocumentIds: [String]
    let onSelect: (String) -> Void  // workflowId

    var body: some View {
        List(workflows) { workflow in
            Button(workflow.name) {
                onSelect(workflow.id)
            }
        }
    }
}
```

### Document Picker Sheet
For workflow editor:
```swift
struct DocumentPickerSheet: View {
    let allowsMultiple: Bool
    let onSelect: ([String]) -> Void  // documentIds

    var body: some View {
        // Document browser in picker mode
    }
}
```

### Batch Execution
Unified function:
```swift
func runBatchWorkflow(workflowId: String, documentIds: [String]) async {
    let batch = try await batchService.createAndRunBatch(
        workflowId: workflowId,
        documentIds: documentIds,
        name: generateBatchName(workflow, documentIds.count)
    )

    // Switch to batches sidebar to show progress
    sidebarMode = .batches
    selectedItemId = "batch:\(batch.batchId)"
}
```

## Batches Sidebar Role

### View-Only Monitoring
- Shows active batches with progress
- Shows completed batches with results
- Shows failed batches with errors
- Allows cancellation of running batches

### NOT for Creation
- No "New Batch" button
- No batch configuration UI
- Just monitoring and inspection

**Analogy**: Like Activity Monitor on macOS - you don't "create" processes there, you just monitor them.

## Future Enhancements (Not in Scope)

### Batch Templates
Save common batch configurations:
- "Weekly PDF Export" (specific workflow + folder)
- "Process Inbox" (workflow + smart search)

Could add "New Batch Template" later, but start simple.

### Scheduled Batches
Trigger batches on schedule:
- Run workflow on folder every night
- This is what Schedules are for (separate feature)

### Batch Configuration Options
Advanced settings:
- Parallel vs sequential execution
- Error handling (stop vs continue)
- Resource limits

Can add settings sheet later if needed.

## Related Features

### Schedules
Automated batch triggering:
- Schedule workflow to run on folder daily
- Schedule creates batches automatically

### Triggers
Event-based batch execution:
- When new file added to folder → Run workflow
- Trigger creates batch automatically

**Batches are the execution layer under schedules and triggers.**

## Testing Considerations
- Multi-select in document browser
- Context menu appears with 2+ docs selected
- Workflow picker shows all workflows
- Batch appears in Batches sidebar after creation
- Progress updates in real-time
- Batch completion notification
- Error handling (workflow fails on some docs)
