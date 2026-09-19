//
//  ShellPrimarySelectionTests.swift
//  FicheroTests
//
//  Pins the 2026-08-09 selection-identity fix: the shell's browserSelection
//  handler drew `Set.first` THREE times (entity focus, preview promotion,
//  stale-fetch guard) — hash order, so each draw could name a DIFFERENT
//  element of the same multi-selection, and actions could target a row the
//  user never considered primary. One helper now answers in DOCUMENT ORDER
//  (what the user sees), with a stable lexical fallback for unloaded ids.
//

@testable import Fichero
import Foundation
import Testing

struct ShellPrimarySelectionTests {

    private func doc(_ id: String) -> Document {
        Document(id: id, docType: .file, name: id)
    }

    @Test("primary follows the visible document order, not set hash order")
    func documentOrderWins() {
        let docs = [doc("c"), doc("a"), doc("b")]
        #expect(shellPrimarySelectionId(in: ["a", "b"], orderedBy: docs) == "a")
        #expect(shellPrimarySelectionId(in: ["b", "c"], orderedBy: docs) == "c")
    }

    @Test("ids not in the loaded list fall back to the stable lexical minimum")
    func unloadedFallsBackStably() {
        #expect(shellPrimarySelectionId(in: ["z-late", "m-mid"], orderedBy: []) == "m-mid")
        // Deterministic across calls — the property Set.first lacks.
        for _ in 0..<10 {
            #expect(shellPrimarySelectionId(in: ["z", "y", "x"], orderedBy: []) == "x")
        }
    }

    @Test("empty selection has no primary")
    func emptyIsNil() {
        #expect(shellPrimarySelectionId(in: [], orderedBy: [doc("a")]) == nil)
    }

    @Test("a partially-loaded selection still prefers the visible member")
    func partiallyLoadedPrefersVisible() {
        // "z-visible" is on screen; "a-unloaded" would win the lexical
        // fallback — visibility must win over lexical order.
        #expect(
            shellPrimarySelectionId(in: ["a-unloaded", "z-visible"], orderedBy: [doc("z-visible")])
                == "z-visible"
        )
    }
}

/// #4882 (spec: workflows.selection.library-row-opens-editor): a Library
/// row's single-selected workflow mirror resolves the SAME editor item the
/// sidebar path resolves, without touching `AppViewMode` — through the real
/// `workflowCanvasSelection` function, not a source scan.
struct WorkflowCanvasSelectionTests {
    private func doc(_ id: String, workflow: Bool) -> Document {
        Document(id: id, docType: .file, name: id, prototypeKey: workflow ? "workflow" : nil)
    }

    private let workflows = [WorkflowSidebarItem(id: "wf-1", name: "Extract Names")]

    @Test("a Library row's single selection, a workflow mirror, resolves the editor item")
    func libraryRowWorkflowSelectionResolves() {
        let result = workflowCanvasSelection(
            viewMode: .library(nil),
            singleSelectedDocument: doc("wf-1", workflow: true),
            workflows: workflows
        )
        #expect(result?.id == "wf-1")
        #expect(result?.name == "Extract Names")
    }

    @Test("a non-workflow document resolves nil")
    func nonWorkflowDocumentResolvesNil() {
        let result = workflowCanvasSelection(
            viewMode: .library(nil),
            singleSelectedDocument: doc("d-1", workflow: false),
            workflows: workflows
        )
        #expect(result == nil)
    }

    @Test("the sidebar's own viewMode == .workflow still wins, even over an unrelated Library selection")
    func sidebarModeWins() {
        let sidebarItem = WorkflowSidebarItem(id: "wf-2", name: "Sidebar-Driven")
        let result = workflowCanvasSelection(
            viewMode: .workflow(sidebarItem),
            // A DIFFERENT document is also selected in a Library pane — the
            // sidebar's own mode must win regardless.
            singleSelectedDocument: doc("wf-1", workflow: true),
            workflows: workflows
        )
        #expect(result?.id == "wf-2", "the sidebar-driven selection must win over an unrelated Library row")
    }

    @Test("a multi-selection (the caller passes nil) resolves nil, not a guess at which row")
    func multiSelectionResolvesNil() {
        // The caller's contract: `singleSelectedDocument` is nil for more
        // than one selected id (real call site:
        // `ContentView.singleSelectedWorkflowRowDocument`, gated on
        // `browserSelection.count == 1`) — this function does not itself
        // re-derive "single-ness" from a selection set.
        let result = workflowCanvasSelection(
            viewMode: .library(nil),
            singleSelectedDocument: nil,
            workflows: workflows
        )
        #expect(result == nil)
    }
}

/// #4882: the pure autosave decision, `ContentView.shouldAutoSaveWorkflow`,
/// and the load-race guard shape it protects. Through the real function.
struct ShouldAutoSaveWorkflowTests {
    private func item(_ id: String) -> WorkflowSidebarItem {
        WorkflowSidebarItem(id: id, name: id)
    }

    @Test("leaving a workflow with unsaved edits saves it")
    func leavingWithEditsSaves() {
        #expect(ContentView.shouldAutoSaveWorkflow(
            old: item("A"), new: nil, isDirty: true, editingWorkflowId: "A", hasBaseline: true
        ))
        #expect(ContentView.shouldAutoSaveWorkflow(
            old: item("A"), new: item("B"), isDirty: true, editingWorkflowId: "A", hasBaseline: true
        ))
    }

    @Test("A to A (the same workflow) never saves, dirty or not")
    func sameWorkflowNeverSaves() {
        #expect(!ContentView.shouldAutoSaveWorkflow(
            old: item("A"), new: item("A"), isDirty: true, editingWorkflowId: "A", hasBaseline: true
        ))
        #expect(!ContentView.shouldAutoSaveWorkflow(
            old: item("A"), new: item("A"), isDirty: false, editingWorkflowId: "A", hasBaseline: true
        ))
    }

    @Test("nil to A (nothing was active) never saves")
    func nilToActiveNeverSaves() {
        #expect(!ContentView.shouldAutoSaveWorkflow(
            old: nil, new: item("A"), isDirty: true, editingWorkflowId: "A", hasBaseline: true
        ))
        #expect(!ContentView.shouldAutoSaveWorkflow(
            old: nil, new: item("A"), isDirty: false, editingWorkflowId: "A", hasBaseline: true
        ))
    }

    @Test("A to B saves A only when A had unsaved edits")
    func differentWorkflowSavesOnlyWhenDirty() {
        #expect(ContentView.shouldAutoSaveWorkflow(
            old: item("A"), new: item("B"), isDirty: true, editingWorkflowId: "A", hasBaseline: true
        ))
        #expect(!ContentView.shouldAutoSaveWorkflow(
            old: item("A"), new: item("B"), isDirty: false, editingWorkflowId: "A", hasBaseline: true
        ))
    }

    /// HOLE 2 (2026-09-19): the editor's ACTUAL id must match `old` — a slow
    /// `getWorkflow(A)` that never completed (or a stale-discarded/failed
    /// load) leaves `editingWorkflow` holding a DIFFERENT workflow's
    /// content, and `isDirty` alone cannot see that — `autoSaveWorkflow`'s
    /// real save target is `editingWorkflow.id`, not `old.id`, so saving
    /// here would silently write the wrong content under the wrong belief.
    @Test("autosave is refused when the editor holds a different workflow than the outgoing one")
    func refusedWhenEditorHoldsADifferentWorkflow() {
        // Dirty (against SOME baseline) and leaving A, but the editor's own
        // id is C — a third, unrelated workflow (or a load for A that never
        // landed, leaving the PREVIOUS workflow's content in place).
        #expect(!ContentView.shouldAutoSaveWorkflow(
            old: item("A"), new: item("B"), isDirty: true, editingWorkflowId: "C", hasBaseline: true
        ))
        // Even leaving to nothing (quit / deselect) — same refusal.
        #expect(!ContentView.shouldAutoSaveWorkflow(
            old: item("A"), new: nil, isDirty: true, editingWorkflowId: "C", hasBaseline: true
        ))
    }

    /// HOLE 3 (2026-09-19): NEVER autosave without a baseline —
    /// `lastSyncedWorkflow == nil` means `old` was never successfully
    /// loaded, so there is nothing of the user's to save; a failed load's
    /// placeholder can otherwise pass the id-match check (HOLE 2) and still
    /// overwrite real server content with near-empty content.
    @Test("no baseline refuses even when dirty and the ids match")
    func noBaselineRefusesEvenWhenDirtyAndIdsMatch() {
        #expect(!ContentView.shouldAutoSaveWorkflow(
            old: item("A"), new: item("B"), isDirty: true, editingWorkflowId: "A", hasBaseline: false
        ))
        #expect(!ContentView.shouldAutoSaveWorkflow(
            old: item("A"), new: nil, isDirty: true, editingWorkflowId: "A", hasBaseline: false
        ))
    }
}

/// #4882 HOLE 1 (2026-09-19): `ContentView.workflowChangeAction` — a
/// same-id field change (rename, nodeCount bump, any `workflowStore
/// .workflows` refresh reaching the Library path's `activeWorkflowItem`)
/// must NOT reload and clobber unsaved edits; only a genuine id change
/// loads.
struct WorkflowChangeActionTests {
    @Test("the same id, even with different fields, aligns metadata only — never reloads")
    func sameIdAlignsMetadataOnly() {
        #expect(ContentView.workflowChangeAction(oldId: "A", newId: "A") == .alignMetadataOnly)
    }

    @Test("a genuine id change loads")
    func idChangeLoads() {
        #expect(ContentView.workflowChangeAction(oldId: "A", newId: "B") == .load)
        #expect(ContentView.workflowChangeAction(oldId: nil, newId: "A") == .load)
    }

    @Test("no new item does nothing, whatever the old one was")
    func noNewItemDoesNothing() {
        #expect(ContentView.workflowChangeAction(oldId: "A", newId: nil) == .none)
        #expect(ContentView.workflowChangeAction(oldId: nil, newId: nil) == .none)
    }
}

/// #4882: the stale-load race guard, `MainContentModifiers.isStaleWorkflowLoad`
/// — a slow `getWorkflow(A)` that returns after the user has moved to B must
/// discard A's answer rather than overwrite `editingWorkflow`.
struct IsStaleWorkflowLoadTests {
    @Test("a result for the most recently requested id is NOT stale")
    func currentResultIsNotStale() {
        #expect(!MainContentModifiers.isStaleWorkflowLoad(resultId: "A", mostRecentlyRequestedId: "A"))
    }

    @Test("a result for a superseded id IS stale and must be discarded")
    func supersededResultIsStale() {
        // The user moved from A to B before A's slow getWorkflow returned.
        #expect(MainContentModifiers.isStaleWorkflowLoad(resultId: "A", mostRecentlyRequestedId: "B"))
    }

    @Test("a result when nothing is currently loading is stale")
    func resultWithNothingLoadingIsStale() {
        #expect(MainContentModifiers.isStaleWorkflowLoad(resultId: "A", mostRecentlyRequestedId: nil))
    }
}

/// F2 (page-1 snapback) and F4 (right-click targeting) shipped without
/// tests; both fix symptoms Daniel reported personally, so a silent
/// regression is indistinguishable from the original bug. Source pins —
/// the F2 handler mutates @State and the F4 resolver is private, so the
/// RULE is pinned where it lives.
struct ReportedSymptomRegressionPins {

    private func source(_ repoRelative: String) throws -> String {
        let root = try AppSource.root()
            .deletingLastPathComponent()   // fichero/ (product dir)
        return try String(contentsOf: root.appendingPathComponent(repoRelative), encoding: .utf8)
    }

    @Test("F2: page focus clears only when the document IDENTITY changes")
    func pageFocusClearIsIdentityGated() throws {
        let events = try source("fichero/Views/Shell/ContentView/ContentView+StateEvents.swift")
        #expect(
            events.contains("if oldDoc?.id != newDoc?.id {"),
            "the unconditional pageFocusDocument clear is back — every background refresh snaps the reader to page 1 (#4558)"
        )
        #expect(events.contains("func handleDetailDocumentChange(from oldDoc: Document?, to newDoc: Document?)"))
    }

    @Test("F4: right-click targets follow the clicked-row rule")
    func rightClickTargetsClickedRow() throws {
        let menu = try source("fichero/Views/Library/LibraryView+ContextMenu.swift")
        #expect(
            menu.contains("selection.contains(document.id) ? Array(selection) : [document.id]"),
            "excludeToggleTargets reverted to selection-wins — right-click acts on rows the user never pointed at"
        )
        #expect(
            !menu.contains("selection.isEmpty ? [document.id] : Array(selection)"),
            "the inverted (selection-wins) form is back"
        )
    }

    @Test("F3: no shell surface draws a primary from Set.first any more")
    func noPrimaryDrawsRemain() throws {
        for path in [
            "fichero/Views/Shell/ContentView/ContentView+StatePreview.swift",
            "fichero/Views/Shell/ContentView/ContentView+StateSelection.swift",
            "fichero/Views/Shell/ContentView/Layout/ContentView+CompactReader.swift",
            "fichero/Models/LayoutMode.swift"
        ] {
            let text = try source(path)
            #expect(!text.contains("browserSelection.first"), "hash-order draw back in \(path)")
            #expect(!text.contains("selectedDocumentIds.first"), "hash-order draw back in \(path)")
        }
    }
}
