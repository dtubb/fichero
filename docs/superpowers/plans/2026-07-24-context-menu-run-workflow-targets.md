# Context-menu Run Workflow Targets Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Sidebar and Library file/folder context menus to run one workflow over selected files plus direct child files of selected folders.

**Architecture:** Add one pure resolver that converts a context-clicked target and active selection into unique direct file IDs. Both existing context menus call it before rendering their existing workflow/provider submenu and pass its IDs through the existing batch/SSE execution path; no workflow execution path changes.

**Tech Stack:** Swift, SwiftUI, XCTest/source-contract tests, existing Fichero workflow stream services.

## Global Constraints

- Folder targets include direct child files only; never recurse.
- A selected click uses the complete selection; an unselected click ignores stale selection.
- Multiple folders aggregate into one de-duplicated workflow run.
- Empty folders offer no Run Workflow action.
- Reuse existing workflow/provider grouping and batch/SSE executor.
- Do not change workflow-catalogue menus, engine APIs, Activity behavior, or workflow execution semantics.

---

## File structure

- Create: `fichero/fichero/Models/WorkflowRunTargetResolver.swift` — pure target/selection resolution.
- Create: `fichero/fichero-tests/WorkflowRunTargetResolverTests.swift` — resolver edge cases.
- Modify: `fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift` — use resolved targets for file/folder Run Workflow context menu.
- Modify: `fichero/fichero/Views/Library/LibraryView+FilterAndBatch.swift` — resolve context targets before the existing workflow submenu/batch state assignment.
- Modify/Test: the existing focused context-menu source-contract test file, or create `fichero/fichero-tests/WorkflowContextMenuTargetsTests.swift` if none exists.

### Task 1: Add the pure workflow target resolver

**Files:**
- Create: `fichero/fichero/Models/WorkflowRunTargetResolver.swift`
- Test: `fichero/fichero-tests/WorkflowRunTargetResolverTests.swift`

**Interfaces:**
- Produces `WorkflowRunTargetResolver.resolve(clicked:selection:documents:) -> [String]`.
- `clicked` is the context-clicked library item identity; `selection` is the active item identities; `documents` is the current document collection.
- Later UI tasks use a nonempty return value as the exact document-ID set for one existing workflow run.

- [ ] **Step 1: Write failing resolver tests**

```swift
func testFileResolvesToItself() {
    XCTAssertEqual(
        WorkflowRunTargetResolver.resolve(
            clicked: .file("a"), selection: [], documents: documents
        ),
        ["a"]
    )
}

func testFolderIncludesOnlyDirectFiles() {
    XCTAssertEqual(
        WorkflowRunTargetResolver.resolve(
            clicked: .folder("/letters"), selection: [], documents: documents
        ),
        ["a", "b"]
    )
}

func testNestedFilesAreExcluded() {
    XCTAssertFalse(
        WorkflowRunTargetResolver.resolve(
            clicked: .folder("/letters"), selection: [], documents: documents
        ).contains("nested")
    )
}

func testSelectedFileAndFolderUnionIsDeduplicated() {
    XCTAssertEqual(
        WorkflowRunTargetResolver.resolve(
            clicked: .folder("/letters"),
            selection: [.file("a"), .folder("/letters")],
            documents: documents
        ),
        ["a", "b"]
    )
}

func testUnselectedClickIgnoresUnrelatedSelection() {
    XCTAssertEqual(
        WorkflowRunTargetResolver.resolve(
            clicked: .folder("/letters"), selection: [.file("outside")], documents: documents
        ),
        ["a", "b"]
    )
}

func testEmptyFolderResolvesToNoDocuments() {
    XCTAssertTrue(
        WorkflowRunTargetResolver.resolve(
            clicked: .folder("/empty"), selection: [], documents: documents
        ).isEmpty
    )
}
```

- [ ] **Step 2: Run the tests to confirm they fail**

Run:
```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme FicheroTests -destination 'platform=macOS' -only-testing:FicheroTests/WorkflowRunTargetResolverTests test
```

Expected: FAIL because `WorkflowRunTargetResolver` is absent.

- [ ] **Step 3: Implement the minimal resolver**

```swift
enum WorkflowRunTargetResolver {
    static func resolve(
        clicked: WorkflowRunTarget,
        selection: Set<WorkflowRunTarget>,
        documents: [Document]
    ) -> [String] {
        let targets = selection.contains(clicked) ? selection : [clicked]
        let directFiles = targets.flatMap { target in
            target.directFileIDs(from: documents)
        }
        return Array(NSOrderedSet(array: directFiles)) as? [String] ?? []
    }
}
```

Implement `directFileIDs(from:)` so `.file(id)` returns only `id`; `.folder(path)` returns only file documents whose parent folder is exactly `path`; it must not match descendants.

- [ ] **Step 4: Run resolver tests and lint**

Run:
```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme FicheroTests -destination 'platform=macOS' -only-testing:FicheroTests/WorkflowRunTargetResolverTests test
swiftlint lint fichero/fichero/Models/WorkflowRunTargetResolver.swift fichero/fichero-tests/WorkflowRunTargetResolverTests.swift
```

Expected: tests PASS and SwiftLint reports 0 violations in touched files.

- [ ] **Step 5: Commit the resolver**

```bash
git add fichero/fichero/Models/WorkflowRunTargetResolver.swift fichero/fichero-tests/WorkflowRunTargetResolverTests.swift
git commit -m "feat(workflows): resolve context-menu folder targets"
```

### Task 2: Wire Sidebar file/folder context menus to resolved targets

**Files:**
- Modify: `fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift`
- Test: `fichero/fichero-tests/WorkflowContextMenuTargetsTests.swift`

**Interfaces:**
- Consumes `WorkflowRunTargetResolver.resolve(clicked:selection:documents:) -> [String]` from Task 1.
- Produces Sidebar context-menu state that invokes the existing `runWorkflowOnDocument`/batch workflow path with resolved IDs.

- [ ] **Step 1: Write a failing Sidebar source-contract test**

```swift
func testSidebarContextMenuResolvesFileAndFolderTargetsBeforeShowingWorkflowMenu() throws {
    let source = try String(contentsOf: sidebarPresentationURL)
    XCTAssertTrue(source.contains("WorkflowRunTargetResolver.resolve"))
    XCTAssertFalse(source.contains("if case .document(let doc) = item.itemType"))
    XCTAssertTrue(source.contains("!workflowTargetIDs.isEmpty"))
}
```

- [ ] **Step 2: Run the targeted test to confirm it fails**

Run:
```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme FicheroTests -destination 'platform=macOS' -only-testing:FicheroTests/WorkflowContextMenuTargetsTests/testSidebarContextMenuResolvesFileAndFolderTargetsBeforeShowingWorkflowMenu test
```

Expected: FAIL because Sidebar still restricts Run Workflow to `.document`.

- [ ] **Step 3: Wire the Sidebar menu**

Replace the document-only guard with resolver-derived `workflowTargetIDs`. Render the existing workflow submenu only when IDs are nonempty. Assign those IDs to the existing batch state and invoke the existing execution callback once per chosen workflow/provider override. Do not alter menu grouping or workflow execution implementation.

- [ ] **Step 4: Run targeted coverage and lint**

Run:
```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme FicheroTests -destination 'platform=macOS' -only-testing:FicheroTests/WorkflowContextMenuTargetsTests test
swiftlint lint fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift fichero/fichero-tests/WorkflowContextMenuTargetsTests.swift
```

Expected: tests PASS and SwiftLint reports 0 violations in touched files.

- [ ] **Step 5: Commit the Sidebar wiring**

```bash
git add fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift fichero/fichero-tests/WorkflowContextMenuTargetsTests.swift
git commit -m "feat(sidebar): run workflows from folder menus"
```

### Task 3: Wire Library file/folder context menus to resolved targets

**Files:**
- Modify: `fichero/fichero/Views/Library/LibraryView+FilterAndBatch.swift`
- Modify: `fichero/fichero-tests/WorkflowContextMenuTargetsTests.swift`

**Interfaces:**
- Consumes `WorkflowRunTargetResolver.resolve(clicked:selection:documents:) -> [String]` from Task 1.
- Uses existing `selectedDocumentIdsForBatch` and `runBatchWorkflow(workflowId:providerOverride:modelOverride:)`.

- [ ] **Step 1: Extend the failing Library source-contract test**

```swift
func testLibraryContextMenuResolvesClickedFolderBeforeBatchWorkflow() throws {
    let source = try String(contentsOf: libraryFilterAndBatchURL)
    XCTAssertTrue(source.contains("WorkflowRunTargetResolver.resolve"))
    XCTAssertTrue(source.contains("selectedDocumentIdsForBatch = workflowTargetIDs"))
    XCTAssertTrue(source.contains("!workflowTargetIDs.isEmpty"))
}
```

- [ ] **Step 2: Run the targeted test to confirm it fails**

Run:
```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme FicheroTests -destination 'platform=macOS' -only-testing:FicheroTests/WorkflowContextMenuTargetsTests/testLibraryContextMenuResolvesClickedFolderBeforeBatchWorkflow test
```

Expected: FAIL because Library maps selection directly to document IDs.

- [ ] **Step 3: Wire the Library menu**

Resolve the clicked file/folder and selected target set before rendering the existing Run Workflow submenu. Set `selectedDocumentIdsForBatch` from the resolver result immediately before calling the existing `runBatchWorkflow`. Do not change `runBatchWorkflow`, its active-library guard, SSE listener, provider/model selection, or refresh logic.

- [ ] **Step 4: Run resolver, context-menu, and lint coverage**

Run:
```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme FicheroTests -destination 'platform=macOS' -only-testing:FicheroTests/WorkflowRunTargetResolverTests -only-testing:FicheroTests/WorkflowContextMenuTargetsTests test
swiftlint lint fichero/fichero/Models/WorkflowRunTargetResolver.swift fichero/fichero/Views/Sidebar/ItemRow/SidebarItemRow+Presentation.swift fichero/fichero/Views/Library/LibraryView+FilterAndBatch.swift fichero/fichero-tests/WorkflowRunTargetResolverTests.swift fichero/fichero-tests/WorkflowContextMenuTargetsTests.swift
git diff --check
```

Expected: all targeted tests PASS, SwiftLint reports 0 violations in touched files, and diff check exits 0.

- [ ] **Step 5: Commit the Library wiring**

```bash
git add fichero/fichero/Views/Library/LibraryView+FilterAndBatch.swift fichero/fichero-tests/WorkflowContextMenuTargetsTests.swift
git commit -m "feat(library): run workflows from folder menus"
```

### Task 4: Manual macOS context-menu acceptance check

**Files:**
- No code changes.

**Interfaces:**
- Validates the exact context-menu affordance wired in Tasks 2–3.

- [ ] **Step 1: Build the app once after all implementation commits**

Run from an interactive macOS/Xcode session:
```bash
xcodebuild -project fichero/fichero.xcodeproj -scheme 'Fichero (Dev Embedded)' -destination 'platform=macOS' build
```

Expected: `BUILD SUCCEEDED`.

- [ ] **Step 2: Verify Sidebar behavior manually**

1. Open a library with a workflow and a folder containing direct files plus a nested subfolder.
2. Right-click the folder in Sidebar.
3. Confirm **Run Workflow** appears only when direct files exist.
4. Choose a workflow and confirm the resulting run receives direct files only.
5. Right-click an unselected folder while another item is selected; confirm only the clicked folder’s direct files run.

- [ ] **Step 3: Verify Library behavior manually**

1. Right-click the same folder in Library grid/list.
2. Confirm the same Run Workflow availability and direct-child scope.
3. Multi-select one file and one folder; right-click a selected target and confirm the run receives the de-duplicated union once.

- [ ] **Step 4: Record validation in the issue**

Post the exact build result and manual acceptance outcome to the existing workflow consistency issue before closing it.
