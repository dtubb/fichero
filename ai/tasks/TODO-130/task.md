# TODO-130: Implement Contextual Batch Triggering

## What to do
Add contextual ways to trigger batch workflow execution on multiple documents (context menu, toolbar button, menu item) rather than requiring explicit batch creation UI. Batches sidebar remains view-only for monitoring.

## Steps
- [ ] Step 1: Add "Run Workflow..." context menu item to document browser (when 2+ docs selected)
- [ ] Step 2: Create workflow picker sheet that appears when "Run Workflow..." is selected
- [ ] Step 3: Implement batch creation + execution when workflow is selected
- [ ] Step 4: Add "Run on Documents..." button to workflow detail view
- [ ] Step 5: Add Data menu item "Run Workflow on Selection..." (enabled when docs selected)
- [ ] Step 6: Show batch progress in Batches sidebar automatically
- [ ] Step 7: Add keyboard shortcut (e.g., ⌘⇧R) for "Run Workflow on Selection"

## Files
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Views/Browser/DocumentBrowserView.swift` (context menu)
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Views/Workflow/WorkflowDetailView.swift` (Run on Docs button)
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/FicheroApp.swift` (Data menu item)
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Views/Sheets/WorkflowPickerSheet.swift` (new file)
- `/Users/dtubb/code/fichero_main/fichero/Fichero/Fichero/Services/BatchService.swift` (verify API)

## Questions for Human
- [ ] Question 1: Should workflow picker show all workflows or filter by compatibility with selected docs?
    Answer: Show all workflows - let user decide, workflow execution will handle incompatibilities
- [ ] Question 2: Should batch start immediately or allow configuration (batch name, options)?
    Answer: Start immediately with auto-generated name - advanced users can use API later
- [ ] Question 3: Should we show a confirmation before starting batch?
    Answer: No confirmation - action is reversible (can cancel batch), fast feedback is better

## Implementation Notes

### User Flow 1: From Document Browser
```
1. User selects 10 PDFs in browser
2. Right-click → "Run Workflow..."
3. Sheet appears with workflow list
4. User clicks "Extract Text Workflow"
5. Sheet closes
6. Batch created with name "Extract Text Workflow - 10 documents"
7. Batch starts executing
8. User switches to Batches sidebar to monitor progress
```

### User Flow 2: From Workflow Editor
```
1. User opens "Extract Text Workflow"
2. Clicks toolbar button "Run on Documents..."
3. Document picker appears
4. User selects 10 PDFs
5. Picker closes
6. Batch created and started
7. User switches to Batches sidebar to monitor
```

### User Flow 3: From Menu Bar
```
1. User selects 10 PDFs in browser
2. Data menu → "Run Workflow on Selection..." (⌘⇧R)
3. Workflow picker appears
4. User selects workflow
5. Batch starts
```

### Backend API Check
Verify `BatchService` has method:
```swift
func createAndRunBatch(
    workflowId: String,
    documentIds: [String],
    name: String?
) async throws -> BatchInfo
```

If not, add it to backend first.

### Code Snippets

#### Document Browser Context Menu
```swift
// DocumentBrowserView.swift
.contextMenu {
    if selectedDocuments.count >= 2 {
        Button {
            showWorkflowPicker = true
        } label: {
            Label("Run Workflow...", systemImage: "play.circle")
        }
    }
    // ... existing menu items
}
.sheet(isPresented: $showWorkflowPicker) {
    WorkflowPickerSheet(
        selectedDocumentIds: selectedDocuments.map { $0.id },
        onSelect: { workflowId in
            Task {
                await runBatchWorkflow(workflowId: workflowId)
            }
        }
    )
}
```

#### Workflow Detail View Button
```swift
// WorkflowDetailView.swift - toolbar
ToolbarItem(placement: .primaryAction) {
    Button {
        showDocumentPicker = true
    } label: {
        Label("Run on Documents", systemImage: "play.circle")
    }
}
.sheet(isPresented: $showDocumentPicker) {
    DocumentPickerSheet(
        allowsMultiple: true,
        onSelect: { documentIds in
            Task {
                await runBatchWorkflow(workflowId: workflow.id, documentIds: documentIds)
            }
        }
    )
}
```

#### Data Menu Item
```swift
// FicheroApp.swift - Data menu
CommandGroup {
    // ... existing items

    Divider()

    FocusedRunWorkflowButton()  // Enabled when docs selected
        .keyboardShortcut("r", modifiers: [.command, .shift])
}
```

### Batch Naming Convention
Auto-generate batch names:
```swift
func generateBatchName(workflowName: String, documentCount: Int) -> String {
    let timestamp = DateFormatter.localizedString(from: Date(), dateStyle: .none, timeStyle: .short)
    return "\(workflowName) - \(documentCount) documents - \(timestamp)"
}
```

Examples:
- "Extract Text Workflow - 10 documents - 2:34 PM"
- "Convert to PDF - 5 documents - 9:15 AM"

## Visual Elements

### Workflow Picker Sheet
```
┌─────────────────────────────────┐
│  Run Workflow                   │
├─────────────────────────────────┤
│  Select a workflow to run on    │
│  10 selected documents:         │
│                                 │
│  📋 Extract Text Workflow       │
│  📋 Convert to PDF              │
│  📋 Generate Summaries          │
│                                 │
│              [Cancel]  [Run]    │
└─────────────────────────────────┘
```

### Batch Created Toast (Optional)
```
┌─────────────────────────────────┐
│  ✓ Batch started                │
│  Processing 10 documents...     │
└─────────────────────────────────┘
```

## Need help?
- Verify BatchService API supports this workflow
- Decide on toast notification vs silent execution
- Test batch cancellation and error handling
