# Activity View Bug Batch Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the Activity view so all tabs show live and post-run data correctly, and fix the critical bug where "Run Workflow on Selection" ignores the user's selection.

**Architecture:** Six independent fixes across SwiftUI Activity views, WorkflowExecutionObserver, and the Python backend `sources.py`. Each task is self-contained. Do them in order — Task 1 unblocks Tasks 5 and 6.

**Tech Stack:** Swift/SwiftUI (Activity views, WorkflowExecutionObserver), Python FastAPI (sources.py)

**Issues closed by this plan:** #627, #628 (partial), #629, #630, #631, #632, #634, #636 (partial), #637

---

## File Map

| File | Change |
|---|---|
| `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityDetailView.swift` | Fix liveExecution key lookup |
| `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityLogView.swift` | Fix liveExecution key lookup |
| `fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver.swift` | Add completedExecutions archive |
| `fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver+Events.swift` | Archive instead of 2-second delete |
| `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityOverviewView.swift` | Add per-file doc progress to live card |
| `fichero-swiftui/fichero-swiftui/Views/Workflow/WorkflowOutputLog.swift` | Filter source-tool columns |
| `fichero-api/src/fichero/workflows/tools/sources.py` | collection_tool respects selected_doc_ids |

---

## Task 1: Fix liveExecution key mismatch (#627, #629, #630, #631)

**Root cause:** `ActivityDetailView.liveExecution` does `activeExecutions[selectedRun.id]` but `selectedRun.id` is the **threadId** while `activeExecutions` is keyed by **workflowId**. Every Activity tab that depends on `liveExecution` sees nil and falls through to its empty state. Same bug in `ActivityLogView`.

**Files:**
- Modify: `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityDetailView.swift:19-22`
- Modify: `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityLogView.swift:18-21`

- [ ] **Step 1: Fix liveExecution in ActivityDetailView**

Open `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityDetailView.swift`.

Replace lines 19–22:
```swift
/// Get the live execution if this run is currently active
private var liveExecution: WorkflowExecution? {
    guard selectedRun.isLive else { return nil }
    return executionObserver.activeExecutions[selectedRun.id]
}
```

With:
```swift
/// Live execution — looks up by workflowId (the key used in activeExecutions),
/// then falls back to completedExecutions so post-run tabs keep their data.
private var liveExecution: WorkflowExecution? {
    guard let workflowId = selectedRun.workflowId else { return nil }
    return executionObserver.activeExecutions[workflowId]
        ?? executionObserver.completedExecutions[workflowId]
}
```

- [ ] **Step 2: Fix liveExecution in ActivityLogView**

Open `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityLogView.swift`.

Replace lines 17–21:
```swift
/// Get live execution if this run is currently active
private var liveExecution: WorkflowExecution? {
    guard selectedRun.isLive else { return nil }
    return executionObserver.activeExecutions[selectedRun.id]
}
```

With:
```swift
/// Live/completed execution looked up by workflowId — the actual key.
private var liveExecution: WorkflowExecution? {
    guard let workflowId = selectedRun.workflowId else { return nil }
    return executionObserver.activeExecutions[workflowId]
        ?? executionObserver.completedExecutions[workflowId]
}
```

Note: `completedExecutions` is added in Task 2. This file will fail to compile until Task 2 is done — do both tasks before building.

- [ ] **Step 3: Build (after completing Task 2 first)**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
xcodebuild -workspace fichero-swiftui/fichero-swiftui.xcodeproj/project.xcworkspace \
  -scheme fichero-swiftui -destination 'platform=macOS' \
  -derivedDataPath /tmp/fichero-build build 2>&1 | grep -E "error:|warning:|BUILD"
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 4: Commit**

```bash
git add fichero-swiftui/fichero-swiftui/Views/Activity/ActivityDetailView.swift \
        fichero-swiftui/fichero-swiftui/Views/Activity/ActivityLogView.swift
git commit -m "fix: Activity liveExecution key was threadId, must be workflowId (#627 #629 #630 #631)"
```

---

## Task 2: Archive completed executions so Activity tabs persist (#637)

**Root cause:** In `WorkflowExecutionObserver+Events.swift`, the `.complete`, `.error`, and `.systemicError` event handlers schedule `activeExecutions.removeValue(forKey:)` after 2 seconds. The Activity view opens after the run finishes — the execution is gone before the user looks. Add a `completedExecutions` dict and move entries there instead of deleting.

**Files:**
- Modify: `fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver.swift`
- Modify: `fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver+Events.swift`

- [ ] **Step 1: Add completedExecutions to WorkflowExecutionObserver**

Open `fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver.swift`.

After line 26 (`var fileCompletedCount: Int = 0`), add:

```swift
/// Executions that have finished — kept for the session so Activity tabs
/// remain populated after a run completes. Keyed by workflowId.
var completedExecutions: [String: WorkflowExecution] = [:]
```

- [ ] **Step 2: Update endExecution to archive instead of delete**

In the same file, find `endExecution(workflowId:status:)` (line 115). Replace its body:

```swift
func endExecution(workflowId: String, status: WorkflowStatus = .completed) {
    let statusDesc = String(describing: status)
    workflowExecutionLogger.info("Ending execution tracking: \(workflowId) with status \(statusDesc)")

    if var execution = activeExecutions[workflowId] {
        execution.status = status
        execution.isRunning = false
        activeExecutions[workflowId] = execution

        // Archive so Activity tabs remain readable after the run
        Task { @MainActor in
            try? await Task.sleep(for: .seconds(1))
            if let finished = self.activeExecutions.removeValue(forKey: workflowId) {
                self.completedExecutions[workflowId] = finished
                workflowExecutionLogger.info("Archived completed execution: \(workflowId)")
            }
        }
    }
}
```

- [ ] **Step 3: Remove 2-second auto-deletions from event handlers**

Open `fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver+Events.swift`.

Find the `.complete` case (around line 146). It currently has:
```swift
// Remove from active executions after a delay (let UI update first)
let completedWorkflowId = workflowId
Task { @MainActor in
    try? await Task.sleep(for: .seconds(2))
    self.activeExecutions.removeValue(forKey: completedWorkflowId)
    workflowExecutionLogger.info("Removed completed execution: \(completedWorkflowId)")
}
```

Remove those 7 lines (the Task block). The `.complete` case should end with just setting `execution.isRunning = false` and `activeExecutions[workflowId] = execution`.

Find the `.error` case (around line 175). It has:
```swift
// Remove from active executions after a delay
let failedWorkflowId = workflowId
Task { @MainActor in
    try? await Task.sleep(for: .seconds(2))
    self.activeExecutions.removeValue(forKey: failedWorkflowId)
}
```

Remove those 6 lines.

Find the `.systemicError` case (around line 188). It has:
```swift
// Remove from active executions after a delay
let systemicFailedWorkflowId = workflowId
Task { @MainActor in
    try? await Task.sleep(for: .seconds(2))
    self.activeExecutions.removeValue(forKey: systemicFailedWorkflowId)
}
```

Remove those 6 lines.

After all three removals, the `.complete`, `.error`, and `.systemicError` handlers still update `execution.status` and `execution.isRunning = false` — they just no longer auto-delete.

- [ ] **Step 4: Build**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
xcodebuild -workspace fichero-swiftui/fichero-swiftui.xcodeproj/project.xcworkspace \
  -scheme fichero-swiftui -destination 'platform=macOS' \
  -derivedDataPath /tmp/fichero-build build 2>&1 | grep -E "error:|warning:|BUILD"
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 5: Commit**

```bash
git add fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver.swift \
        fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver+Events.swift
git commit -m "fix: archive completed executions so Activity tabs persist after run (#637)"
```

---

## Task 3: Fix collection_tool to respect selected_doc_ids (#634)

**Root cause:** When the user runs "Run Workflow on Selection" on a Collection→Transcribe workflow, the Collection source node calls `collection_tool` which fetches ALL docs in the folder. It never checks `state["selected_doc_ids"]`, so the selection is ignored and the entire folder runs.

**Fix:** At the start of `collection_tool`, check if `selected_doc_ids` is non-empty. If it is, return only those specific documents instead of fetching the whole collection.

**Files:**
- Modify: `fichero-api/src/fichero/workflows/tools/sources.py:180-243`

- [ ] **Step 1: Write the failing test**

Open `fichero-api/tests/unit/test_sources_selected_doc_ids.py` (create new file):

```python
"""Tests that collection_tool respects selected_doc_ids when present."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fichero.workflows.tools.sources import collection_tool
from fichero.models import Document, DocType


@pytest.fixture
def mock_db():
    db = MagicMock()
    page_a = Document(
        id="page-a", name="page_001.pdf", path="/lib/page_001.pdf",
        doc_type=DocType.page
    )
    page_b = Document(
        id="page-b", name="page_002.pdf", path="/lib/page_002.pdf",
        doc_type=DocType.page
    )
    db.get.side_effect = lambda cls, id: {"page-a": page_a, "page-b": page_b}.get(id)
    return db, page_a, page_b


@pytest.mark.asyncio
async def test_collection_tool_respects_selected_doc_ids(mock_db):
    """When selected_doc_ids is set, return only those docs, not the whole collection."""
    db, page_a, _ = mock_db
    with patch("fichero.workflows.tools.sources.db_manager") as mock_mgr:
        mock_mgr.get_database.return_value = db
        result = await collection_tool(
            inputs={"collection_id": "folder-x"},
            state={
                "library_path": "/lib",
                "selected_doc_ids": ["page-a"],
            },
            llm_config=MagicMock(),
        )
    assert result["count"] == 1
    assert result["files"] == ["/lib/page_001.pdf"]
    assert len(result["documents"]) == 1
    assert result["documents"][0]["id"] == "page-a"


@pytest.mark.asyncio
async def test_collection_tool_no_selected_ids_uses_collection(mock_db):
    """Without selected_doc_ids, collection_tool uses the full collection."""
    db, page_a, page_b = mock_db
    all_docs = [page_a, page_b]
    with patch("fichero.workflows.tools.sources.db_manager") as mock_mgr, \
         patch("fichero.workflows.tools.sources._get_files_in_folder", return_value=all_docs):
        mock_mgr.get_database.return_value = db
        result = await collection_tool(
            inputs={"collection_id": "folder-x"},
            state={"library_path": "/lib"},
            llm_config=MagicMock(),
        )
    assert result["count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/test_sources_selected_doc_ids.py -v
```

Expected: FAIL — `test_collection_tool_respects_selected_doc_ids` fails because collection_tool ignores `selected_doc_ids`.

- [ ] **Step 3: Implement the fix in collection_tool**

Open `fichero-api/src/fichero/workflows/tools/sources.py`.

In `async def collection_tool(...)`, after the `collection_id` empty check (around line 204) and before fetching `library_path`, insert this block:

```python
# Priority 0: UI selection override — if specific doc IDs were selected,
# return only those docs instead of the whole collection.
selected_doc_ids = state.get("selected_doc_ids", [])
if selected_doc_ids:
    library_path = state.get("library_path") or inputs.get("library_path")
    if library_path:
        db = db_manager.get_database(library_path)
        docs = [db.get(Document, doc_id) for doc_id in selected_doc_ids]
        docs = [d for d in docs if d is not None]
        files = [d.path for d in docs if d.path]
        documents = [d.model_dump() for d in docs]
        logger.info(
            f"collection_tool: {len(files)} files from selected_doc_ids "
            f"(overriding collection {collection_id})"
        )
        return {"files": files, "documents": documents, "count": len(files)}
```

Place this block immediately after:
```python
    collection_id = inputs.get("collection_id")
    if not collection_id:
        return {
            "files": [],
            "documents": [],
            "count": 0,
            "error": "No collection_id provided",
        }
```

The `Document` import is already at the top of sources.py (line 21: `from fichero.models import Document, DocType`).

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/test_sources_selected_doc_ids.py -v
```

Expected: both tests PASS.

- [ ] **Step 5: Run full test suite to check for regressions**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
PYTHONPATH=fichero-api/src .venv/bin/pytest fichero-api/tests/unit/ \
  --ignore=fichero-api/tests/unit/_archived -x -q 2>&1 | tail -20
```

Expected: pre-existing failures only (test_providers.py, test_routes_settings.py — 8 known failures).

- [ ] **Step 6: Commit**

```bash
git add fichero-api/src/fichero/workflows/tools/sources.py \
        fichero-api/tests/unit/test_sources_selected_doc_ids.py
git commit -m "fix: collection_tool respects selected_doc_ids — run on selection no longer runs whole folder (#634)"
```

---

## Task 4: Hide source-tool columns in Output Log (#632)

**Root cause:** `WorkflowOutputLog` renders one column per `workflow.nodes` entry. The Collection (source) node never emits `fileStart`/`fileComplete` events, so its column is always "-". Source nodes gather files but don't process them one by one — they shouldn't appear as per-file columns.

**Fix:** Filter `workflow.nodes` to exclude known source tools before building the table.

**Files:**
- Modify: `fichero-swiftui/fichero-swiftui/Views/Workflow/WorkflowOutputLog.swift:103-140`

- [ ] **Step 1: Add a source-tool filter property**

Open `fichero-swiftui/fichero-swiftui/Views/Workflow/WorkflowOutputLog.swift`.

After the `executionState` computed property (around line 27), add:

```swift
/// Nodes to show as Output Log columns — source tools (collection, files,
/// folder, search) gather inputs but never emit per-file events, so they
/// produce an all-"-" column that adds noise without value.
private static let sourceTool: Set<String> = ["files", "collection", "folder", "search"]

private var processingNodes: [WorkflowNode] {
    workflow.nodes.filter { !Self.sourceTool.contains($0.tool) }
}
```

- [ ] **Step 2: Replace workflow.nodes with processingNodes in the table**

In `tableHeaderRow` (around line 103), change:

```swift
ForEach(workflow.nodes) { node in
    Text(node.label ?? node.tool)
```

to:

```swift
ForEach(processingNodes) { node in
    Text(node.label ?? node.tool)
```

In `tableRow(for:)` (around line 122), change:

```swift
ForEach(workflow.nodes) { node in
    stepStatusCell(for: progress.stepStatuses[node.id])
```

to:

```swift
ForEach(processingNodes) { node in
    stepStatusCell(for: progress.stepStatuses[node.id])
```

- [ ] **Step 3: Build**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
xcodebuild -workspace fichero-swiftui/fichero-swiftui.xcodeproj/project.xcworkspace \
  -scheme fichero-swiftui -destination 'platform=macOS' \
  -derivedDataPath /tmp/fichero-build build 2>&1 | grep -E "error:|warning:|BUILD"
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 4: Commit**

```bash
git add fichero-swiftui/fichero-swiftui/Views/Workflow/WorkflowOutputLog.swift
git commit -m "fix: hide source-tool columns (Collection, Files) in Output Log — they never have per-file data (#632)"
```

---

## Task 5: Filter LangGraph internal names from Console and Graph tabs (#628)

**Root cause:** LangGraph emits `nodeBegin` events for internal nodes like `Transcribe_aggregate` and state-update channels like `parallel_results`. These leak through to the Console tab's node list and the Graph tab's checkpoint viewer.

The backend runner already filters `_aggregate` nodes from `nodeBegin` SSE events (they have a `continue` guard). But the Graph tab loads raw checkpoint history from the API which contains raw LangGraph state including `parallel_results` as a state key with hundreds of array entries.

**Fix for Console:** Already handled by backend. If `_aggregate` nodes still appear, add a Swift-side filter.
**Fix for Graph:** Filter known internal channel names from the checkpoint detail view.

**Files:**
- Modify: `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityGraphView.swift`
- Modify: `fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver+Events.swift` (defensive filter)

- [ ] **Step 1: Add internal-name filter to the event observer**

Open `fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver+Events.swift`.

In the `.nodeBegin` case, after `workflowExecutionLogger.info("[EVENT] Node started...")`, add a guard to skip LangGraph internal nodes:

```swift
case .nodeBegin(_, let nodeId, let nodeName):
    workflowExecutionLogger.info("[EVENT] Node started: \(nodeName) (\(nodeId))")
    // Skip LangGraph internal fan-out/fan-in nodes — they're not user-visible steps.
    guard !nodeId.hasSuffix("_aggregate"), !nodeId.hasPrefix("branch:to:") else { break }
    var state = execution.nodeStates[nodeId] ?? NodeExecutionState(nodeId: nodeId)
    state.status = .running
    state.progress = 0
    execution.nodeStates[nodeId] = state
    execution.currentNodeId = nodeId
    execution.currentNodeName = nodeName
    workflowExecutionLogger.info("[EVENT] nodeStates now has \(execution.nodeStates.count) entries")
```

(The existing code doesn't have the guard — add it before the `var state = ...` line.)

- [ ] **Step 2: Filter internal channels in ActivityGraphView checkpoint detail**

Open `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityGraphView.swift`.

Find where the checkpoint's `channelValues` (or equivalent state keys) are displayed. The checkpoint detail view renders LangGraph state keys. Add a filter to skip internal keys:

```swift
/// Keys used internally by LangGraph that are not meaningful to users.
private static let internalChannelKeys: Set<String> = [
    "parallel_results", "__end__", "__start__", "branch:to"
]

private func isInternalKey(_ key: String) -> Bool {
    Self.internalChannelKeys.contains(key) ||
    key.hasSuffix("_aggregate") ||
    key.hasPrefix("branch:to:")
}
```

In the view's channel-rendering loop (wherever it iterates state keys), wrap with:
```swift
.filter { !isInternalKey($0.key) }
```

(You need to find the exact rendering loop in ActivityGraphView.swift — read the full file first to locate it.)

- [ ] **Step 3: Build**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
xcodebuild -workspace fichero-swiftui/fichero-swiftui.xcodeproj/project.xcworkspace \
  -scheme fichero-swiftui -destination 'platform=macOS' \
  -derivedDataPath /tmp/fichero-build build 2>&1 | grep -E "error:|warning:|BUILD"
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 4: Commit**

```bash
git add fichero-swiftui/fichero-swiftui/Services/WorkflowExecutionObserver+Events.swift \
        fichero-swiftui/fichero-swiftui/Views/Activity/ActivityGraphView.swift
git commit -m "fix: filter LangGraph internal node names from Console and Graph tabs (#628)"
```

---

## Task 6: Add per-file document progress grid to Activity Overview (#636)

**Root cause / context:** The Activity Overview shows an empty progress card for live runs when `overallProgress == nil` (no `parallelStart` event). After Task 1 and 2, `liveExecution` is properly populated — but the Overview `liveStatsCard` only shows an overall progress bar and current file. It should also show which files have been processed (like the Progress tab's "Recent Files" list).

**Files:**
- Modify: `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityOverviewView.swift:52-85`

- [ ] **Step 1: Add document progress list to liveStatsCard**

Open `fichero-swiftui/fichero-swiftui/Views/Activity/ActivityOverviewView.swift`.

Replace the `liveStatsCard` function (lines 52–86) with:

```swift
@ViewBuilder
private func liveStatsCard(_ execution: WorkflowExecution) -> some View {
    VStack(alignment: .leading, spacing: 12) {
        Text("Progress")
            .font(.headline)

        if let progress = execution.overallProgress {
            ProgressView(value: progress)
                .scaleEffect(y: 1.5)

            HStack {
                Text("\(Int(progress * 100))%")
                    .font(.title2.monospacedDigit())

                Spacer()

                if execution.totalFiles > 0 {
                    Text("\(execution.processedFiles) of \(execution.totalFiles) files")
                        .foregroundStyle(.secondary)
                }
            }
        } else if execution.totalFiles == 0 && !execution.documentProgress.isEmpty {
            // Files are being processed but no parallelStart count was emitted
            Text("\(execution.processedFiles) files processed")
                .font(.subheadline)
                .foregroundStyle(.secondary)
        } else {
            HStack(spacing: 8) {
                ProgressView().scaleEffect(0.7)
                Text("Starting…")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
            }
        }

        if let currentFile = execution.currentFileName {
            HStack {
                Text("Current:")
                    .foregroundStyle(.secondary)
                Text(currentFile)
                    .lineLimit(1)
            }
            .font(.caption)
        }

        // Per-file summary (up to 8 most recent)
        if !execution.documentProgress.isEmpty {
            Divider()

            Text("Files")
                .font(.subheadline.bold())
                .foregroundStyle(.secondary)

            ForEach(execution.orderedDocumentProgress.prefix(8)) { doc in
                HStack(spacing: 6) {
                    docStatusIcon(doc)
                    Text(doc.documentName)
                        .font(.caption)
                        .lineLimit(1)
                    Spacer()
                }
            }

            if execution.documentProgress.count > 8 {
                Text("+ \(execution.documentProgress.count - 8) more")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }
    .padding()
    .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
}

@ViewBuilder
private func docStatusIcon(_ doc: DocumentProgress) -> some View {
    if doc.stepStatuses.values.contains(where: { if case .failed = $0 { return true }; return false }) {
        Image(systemName: "xmark.circle.fill").foregroundStyle(.red).font(.caption)
    } else if doc.stepStatuses.values.contains(where: { if case .running = $0 { return true }; return false }) {
        ProgressView().scaleEffect(0.5).frame(width: 12, height: 12)
    } else if !doc.stepStatuses.isEmpty {
        Image(systemName: "checkmark.circle.fill").foregroundStyle(.green).font(.caption)
    } else {
        Image(systemName: "circle").foregroundStyle(.secondary).font(.caption)
    }
}
```

- [ ] **Step 2: Build**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
xcodebuild -workspace fichero-swiftui/fichero-swiftui.xcodeproj/project.xcworkspace \
  -scheme fichero-swiftui -destination 'platform=macOS' \
  -derivedDataPath /tmp/fichero-build build 2>&1 | grep -E "error:|warning:|BUILD"
```

Expected: `** BUILD SUCCEEDED **`

- [ ] **Step 3: Lint**

```bash
cd /Users/danieltubb/code/fichero-0.0.2
swiftlint lint fichero-swiftui/fichero-swiftui/Views/Activity/ActivityOverviewView.swift
```

Expected: no errors.

- [ ] **Step 4: Commit**

```bash
git add fichero-swiftui/fichero-swiftui/Views/Activity/ActivityOverviewView.swift
git commit -m "fix: Activity Overview live card shows per-file document progress grid (#636)"
```

---

## Self-Review Checklist

**Spec coverage:**
- ✅ #627 (Log tab empty) — Task 1 fixes liveExecution key
- ✅ #629 (Progress tab empty) — Task 1 + Task 6 (fallback when totalFiles==0)
- ✅ #630 (Console tab empty) — Task 1 fixes liveExecution key
- ✅ #631 (Overview 0 events) — Task 1 fixes liveExecution so liveStatsCard renders
- ✅ #632 (Collection column "-") — Task 4
- ✅ #634 (page selection runs whole folder) — Task 3
- ✅ #636 (no step grid in Overview) — Task 6
- ✅ #637 (data cleared after run) — Task 2
- ✅ #628 (LangGraph names) — Task 5

**Not in scope (need separate investigation):**
- #633 (green checkmarks but no artifacts) — requires tracing how backend stores artifacts for page-type documents; backend artifact storage, not UI wiring
- #635 (console log lines lack filename) — requires backend logging changes to include per-file context in log_execution calls

**Placeholder scan:** No TBDs or "implement later" items. All code shown. All file paths exact.

**Type consistency:** `completedExecutions` added in Task 2 and referenced in Task 1 — correct (Task 1 code references `executionObserver.completedExecutions[workflowId]`). `processingNodes` added in Task 4, used in two ForEach calls — consistent. `docStatusIcon` added in Task 6, referenced in the same file — consistent.
