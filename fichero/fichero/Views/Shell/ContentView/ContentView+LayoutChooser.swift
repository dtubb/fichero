import OSLog
import SwiftUI

private let workspaceSnapshotLogger = Logger(subsystem: "app.fichero.fichero", category: "WindowWorkspace")

// MARK: - The Workspaces menu (Daniel, 2026-09-01)
//
// ONE toolbar button, not three. Split/New Tab, Workspaces and Layouts each
// had their own item, so "how this window is arranged" was spread across
// three menus that had to be found in the right order. They are now sections
// of a single "Workspaces" menu — layouts, split, saved arrangements, toolbar
// buttons — with every verb that was reachable before still reachable.
//
// Small named subviews per the type-checker budget; policy (serialisation,
// presets, split routing) lives in WindowWorkspace.swift as pure testable
// types.

extension ContentView {

    // MARK: Split / New Tab (⊞+)

    /// The focused pane's KIND, from real focus falling back to the last hint — the same signal
    /// the retired `SplitCommandRouting` used, minus the dead slot-id translation (#4685).
    private var focusedPaneKindForSplit: PaneKind? {
        switch focusedPane ?? paneFocusHint {
        case .content: .library
        case .preview: .preview
        case .reading: .reading
        case .chat: .chat
        case .sidebar, .inspector, nil: nil
        }
    }

    /// The id of the FOCUSED leaf in the applied `PaneList` — the first top-level leaf of the
    /// focused kind (spec panes.split.focused-only route target, #4685). Menu Split routes
    /// through THIS id, mutating the model the way close already does via `removingLeaf`. `nil`
    /// when focus is on a surface that isn't in the list (sidebar/inspector) or the focused
    /// kind isn't currently mounted.
    ///
    /// Known residue (tracked, not this change): with two same-kind panes (Compare) this always
    /// resolves to the FIRST one, not necessarily the specific instance under the pointer —
    /// full per-instance precision is spec §"Migration order" increment 4. Every built-in
    /// workspace today has at most one leaf per kind, so this is exact for all of them.
    var focusedLeafID: UUID? {
        guard let kind = focusedPaneKindForSplit else { return nil }
        return activePaneList.leafIDs(of: kind).first
    }

    /// Split the focused leaf along `axis` through the `PaneList` model (spec
    /// panes.split.focused-only) — the symmetric twin of `closeLeaf`/`removingLeaf`. A no-op
    /// when nothing eligible has focus.
    func splitFocusedLeaf(_ axis: SplitAxis) {
        guard let id = focusedLeafID else { return }
        activePaneList = activePaneList.splittingLeaf(id, axis: axis)
        // A split doesn't change the KIND set, but every `activePaneList` writer still ends in
        // the one funnel (#4686/#4687) — this is what makes a split's composition survive the
        // next launch.
        paneListDidChange()
    }

    /// Pure decision core for `canSplitFocusedLeaf` (#4968), over the two facts that decide it —
    /// `nonisolated static` so a non-@MainActor Swift Testing suite can drive the three cases
    /// directly (no focus, an ordinary focused leaf, a focused leaf AT ITS SPLIT CAP) without
    /// standing up a real `ContentView`.
    nonisolated static func canSplit(
        focusedLeafExists: Bool,
        focusedKind: PaneKind?,
        activeWorkflowShown: Bool
    ) -> Bool {
        guard focusedLeafExists else { return false }
        if focusedKind == .preview, activeWorkflowShown {
            return PaneSurface.workflowCanvas.allowsSplit
        }
        return true
    }

    /// #4968: whether the FOCUSED leaf can split right now — a real leaf must be focused, AND
    /// its own surface must allow a second instance. The workflow canvas is the one surface that
    /// refuses (`PaneSurface.workflowCanvas.allowsSplit == false`, #4705 increment 2 — two
    /// `WorkflowEditor`s on one `editingWorkflow` would race their autosave tasks); the pane
    /// head's own split "+" already enforces this (`ContentView+PreviewPaneHead.swift`'s
    /// `previewPaneCanSplit`), so the Workspaces menu's Split commands must agree with it rather
    /// than offering a split the head itself would refuse to draw.
    var canSplitFocusedLeaf: Bool {
        Self.canSplit(
            focusedLeafExists: focusedLeafID != nil,
            focusedKind: focusedPaneKindForSplit,
            activeWorkflowShown: activeWorkflowItem != nil
        )
    }

    // MARK: Workspaces (ONE button — Daniel, 2026-08-31)

    /// The single window-arrangement control (Daniel, 2026-09-01: "merge
    /// split, workspaces and layouts into ONE Workspaces button"). It was
    /// three toolbar items; it is now four sections of one menu — Layouts
    /// (which panes show), Split (new tab / split the focused pane), the
    /// built-in and saved arrangements, and the Toolbar Buttons submenu.
    /// Nothing that was reachable before is gone.
    ///
    /// A workspace now carries the TOOLBAR too: which optional buttons show,
    /// and whether the workflow bar rides along. Three built-in arrangements
    /// ship with the app so the menu is useful before anything is saved.
    var workspacesMenu: some View {
        // #4968: the SAME shared body the View menu's `WorkspaceCommandsSection` renders — this
        // toolbar menu just supplies its own `windowLayoutCommands` directly (it already IS the
        // focused window's ContentView, unlike the View menu, which has to reach it through a
        // FocusedValue). The two can no longer differ in items, wording, order, shortcuts or
        // enabled state, because they are the same view rendering the same input shape.
        Menu {
            WorkspacesMenuBody(commands: windowLayoutCommands)
        } label: {
            Label("Workspaces", systemImage: "rectangle.grid.1x2")
        }
        .help("Apply, save, or delete a window arrangement — panes, splits, "
            + "the workflow and markup bars, and toolbar buttons")
        .accessibilityLabel("Workspaces")
        .alert("Save Workspace", isPresented: Bindable(chromeUX).showSaveWorkspacePrompt) {
            TextField("Name", text: Bindable(chromeUX).workspaceNameDraft)
            Button("Save") {
                WindowWorkspaceStore.shared.save(
                    name: chromeUX.workspaceNameDraft,
                    layout: captureLayoutSnapshot()
                )
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Names this arrangement — panes, widths, splits, the workflow "
                + "and markup bars, and toolbar buttons — so you can apply it "
                + "later.")
        }
    }

    /// Apply a v2 workspace as the window's STORED pane list (spec §"v2 workspace design"). The
    /// ONE built-in workspace system (spec workspaces.one-system): applying one stores it as the
    /// window's pane list (`activePaneList`), which the centre renders directly.
    func applyWorkspaceLayout(_ layout: BuiltInWorkspaceLayout) {
        activePaneList = layout.panes
        // Remember it for the next launch (#4686/#4687) — the funnel every `activePaneList`
        // writer ends in.
        paneListDidChange()
    }

    /// A saved workspace is "active" when the window shows the chrome it
    /// names. Widths and splits are deliberately NOT compared — dragging a
    /// divider a few points should not un-check the workspace you are in.
    private func isActive(
        _ workspace: SavedWindowWorkspace,
        panes: PaneVisibilityPlan,
        toolbar: ToolbarVisibilityPlan
    ) -> Bool {
        workspace.layout.panes == panes
            && workspace.layout.toolbar == toolbar
            && workspace.layout.showWorkflowBar == showWorkflowBar
            && workspace.layout.showAnnotationBar == showAnnotationBar
    }

    // MARK: Capture / apply

    var currentPaneVisibilityPlan: PaneVisibilityPlan {
        // #4687 cascade: `showDocumentGrid`/`showDocumentCanvas`/`showReadingPane` are deleted —
        // this file wasn't in that task's allowed list, but leaving these three names unresolved
        // would not compile, so the same DERIVED substitution used everywhere else lands here too.
        let visibility = paneVisibility
        return PaneVisibilityPlan(
            showSidebar: showSidebar,
            showInspector: showInspectorSidebar,
            showLibraryPane: visibility.grid,
            showPreviewPane: visibility.canvas,
            showReaderPane: visibility.reading,
            showChatPane: showChatPane
        )
    }

    func captureLayoutSnapshot() -> WindowLayoutSnapshot {
        // `paneKindOverrides` is NOT populated here (#4685 leftover cleanup): nothing reads the
        // live `ContentView.paneKindOverrides` dict any more (the last reader,
        // `focusedSplitStorageKey`'s `SplitCommandRouting.storageKey(overrides:)`, was deleted
        // with #4685's split-routing fix), so a NEW snapshot leaves the field at its `[String:
        // String] = [:]` default. The field itself stays on `WindowLayoutSnapshot` — decode-only
        // now — purely so a snapshot saved BEFORE this change still decodes leniently.
        WindowLayoutSnapshot(
            panes: currentPaneVisibilityPlan,
            libraryPaneWidth: widescreenContentPaneWidth,
            readerPaneWidth: pageContentPaneWidth,
            chatPaneWidth: chatPaneWidth,
            splits: paneSplitCoordinator.splitCounts,
            viewDisplayMode: viewDisplayMode.rawValue,
            layoutMode: currentLayoutMode.rawValue,
            toolbar: WindowWorkspaceStore.shared.toolbarVisibility,
            showWorkflowBar: showWorkflowBar,
            showAnnotationBar: showAnnotationBar,
            // #4686: the ACTUAL composition, not a re-derivation of the legacy Bools above —
            // this is what makes "Save Current as Workspace…" capture what is really on screen,
            // including a workspace's own splits (`activePaneList` already carries them).
            paneList: activePaneList
        )
    }

    /// Applies a full saved arrangement, with the same snappy animation the
    /// pane toggles use. Pane visibility routes through the existing setters
    /// so the #1696 ≥1-visible-pane invariant keeps holding.
    func applyLayoutSnapshot(_ snapshot: WindowLayoutSnapshot) {
        withAnimation(FrameAnimation.snappy) {
            applyPaneVisibilityPlan(snapshot.panes)
            widescreenContentPaneWidth = snapshot.libraryPaneWidth
            pageContentPaneWidth = snapshot.readerPaneWidth
            chatPaneWidth = snapshot.chatPaneWidth
            // `snapshot.paneKindOverrides` is NOT applied here (#4685 leftover cleanup, same
            // reasoning as `captureLayoutSnapshot`): nothing reads the live dict this would have
            // populated, so restoring it accomplishes nothing. Only relevant to an old snapshot
            // that HAS the field — which now just goes unused rather than round-tripped.
            if let mode = LayoutMode(rawValue: snapshot.layoutMode) {
                updateLayoutMode(mode)
            }
            if let display = ViewDisplayMode(rawValue: snapshot.viewDisplayMode) {
                updateViewDisplayMode(display)
            }
            showWorkflowBar = snapshot.showWorkflowBar
            showAnnotationBar = snapshot.showAnnotationBar
            // #4686: apply the REAL composition — before this, applying a saved workspace
            // never touched `activePaneList` at all, so it changed nothing visible.
            if let paneList = snapshot.paneList {
                activePaneList = paneList
                paneListDidChange()
            } else {
                // A snapshot saved before #4686 has no stored composition — falling back to
                // the Read default (rather than leaving `activePaneList` untouched, which would
                // silently keep showing whatever the window had) and saying so, per "prefer raise
                // over silent fallback": this IS a fallback, but a logged, deliberate one.
                workspaceSnapshotLogger.notice("Saved arrangement predates the pane-list model (#4686) — applying the Read default instead of its recorded composition.")
                activePaneList = BuiltInWorkspaceLayout.read.panes
                paneListDidChange()
            }
        }
        paneSplitCoordinator.applySplits(snapshot.splits)
        // Toolbar last, and outside the animation: it is app-wide chrome, not
        // this window's geometry, and re-laying the NSToolbar mid-animation is
        // exactly the kind of churn #3163 taught us to keep off the critical
        // path.
        WindowWorkspaceStore.shared.setToolbarVisibility(snapshot.toolbar)
    }

    private func applyPaneVisibilityPlan(_ plan: PaneVisibilityPlan) {
        guard plan.isValid else { return }
        // ON before OFF, so the #1696 "never hide the last visible pane"
        // refusal cannot fire mid-apply on a plan that is valid overall.
        if plan.showLibraryPane { setLibraryPaneVisible(true) }
        if plan.showPreviewPane { setCanvasPaneVisible(true) }
        if plan.showReaderPane { setReadingPaneVisible(true) }
        if !plan.showLibraryPane { setLibraryPaneVisible(false) }
        if !plan.showPreviewPane { setCanvasPaneVisible(false) }
        if !plan.showReaderPane { setReadingPaneVisible(false) }
        setChatPaneVisible(plan.showChatPane)
        showSidebar = plan.showSidebar
        updateColumnVisibility()
        showInspectorSidebar = plan.showInspector
    }

    // MARK: Focused-window commands (menu bar)

    /// Published via `focusedSceneValue` so the View menu's workspace section
    /// acts on the focused window (same mechanism as InspectorButton).
    var windowLayoutCommands: WindowLayoutCommands {
        WindowLayoutCommands(
            saveWorkspace: {
                chromeUX.workspaceNameDraft = ""
                chromeUX.showSaveWorkspacePrompt = true
            },
            applyWorkspace: { applyLayoutSnapshot($0.layout) },
            applyWorkspaceLayout: { applyWorkspaceLayout($0) },
            // Split/New Tab (#4685): given a menu-bar home here alongside the toolbar's, both
            // routing through the same `PaneList` verbs — `splitFocusedLeaf` on THIS window.
            splitFocusedLeaf: { splitFocusedLeaf($0) },
            newTab: {
                WindowOpener.open(libraryId: windowState.libraryId, asTab: true, using: openWindow)
            },
            canSplitFocusedLeaf: canSplitFocusedLeaf,
            // #4968: cheaply available (already computed for the toolbar's own use) — lets a
            // Split row say WHAT it splits ("Split Library Right") in both menus alike, instead
            // of a bare "Split Right".
            focusedPaneKindForSplit: focusedPaneKindForSplit,
            // #4968: the toolbar's own `isActive` check, now reachable from either menu so the
            // active-workspace checkmark stops being a toolbar-only feature.
            isWorkspaceActive: { workspace in
                isActive(workspace, panes: currentPaneVisibilityPlan, toolbar: WindowWorkspaceStore.shared.toolbarVisibility)
            }
        )
    }
}

/// The focused window's workspace verbs, for the menu bar.
///
/// Equatable is LOAD-BEARING (the RunWorkflowOnSelectionKey lesson): a
/// non-Equatable focused value is byte-compared per body pass, always reads
/// as changed, and cascades focus invalidations. #4968: a blanket `{ true }`
/// (the ORIGINAL fix for that churn) went too far — it also froze
/// `canSplitFocusedLeaf` for `@FocusedValue` consumers, since SwiftUI skips
/// republishing a focused value it considers unchanged, so the View menu's
/// Split rows kept whatever enabled state they had the FIRST time a window
/// published one and never saw a real focus change again (#4968's own
/// diagnosis: "likely the menu bar reads a focused value that is not set" —
/// more precisely, one that never gets marked changed). Comparing the two
/// DATA fields that can actually differ keeps the churn-dampening (an
/// unrelated re-render, same two values, still compares equal — no
/// downstream invalidation) while letting a REAL change through (either
/// value flips → not equal → republished, so the menu's enabled state and
/// its "Split WHAT" wording both stay live). The closures are deliberately
/// excluded from the comparison: they are recreated with a new identity on
/// every `windowLayoutCommands` evaluation regardless of whether anything
/// meaningful changed, so comparing them would reintroduce the exact churn
/// the original blanket `true` was added to dampen.
struct WindowLayoutCommands: Equatable {
    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.canSplitFocusedLeaf == rhs.canSplitFocusedLeaf
            && lhs.focusedPaneKindForSplit == rhs.focusedPaneKindForSplit
    }

    let saveWorkspace: @MainActor () -> Void
    let applyWorkspace: @MainActor (SavedWindowWorkspace) -> Void
    /// Apply a v2 built-in workspace (the one built-in system) to the focused window — sets its
    /// `activePaneList` (spec workspaces.one-system). This is what ⌘⌥1–5 drives from the menu bar.
    let applyWorkspaceLayout: @MainActor (BuiltInWorkspaceLayout) -> Void
    /// Split the focused window's focused leaf through the `PaneList` model (spec
    /// panes.split.focused-only, #4685) — the menu-bar twin of the toolbar's Split Right/Below.
    let splitFocusedLeaf: @MainActor (SplitAxis) -> Void
    /// Open this library in a new tab of the focused window (#4685: given a menu-bar home
    /// alongside the toolbar's, per the addendum on #4685).
    let newTab: @MainActor () -> Void
    /// Whether the focused window currently has an eligible focused leaf to split.
    let canSplitFocusedLeaf: Bool
    /// #4968: the focused pane's kind, when the window makes it cheaply available — lets a Split
    /// row name its target ("Split Library Right") instead of a bare "Split Right". `nil` when no
    /// pane has focus, matching `canSplitFocusedLeaf == false` in that case.
    let focusedPaneKindForSplit: PaneKind?
    /// #4968: whether a saved workspace matches what this window currently shows — the checkmark
    /// both menus now display identically (previously toolbar-only).
    let isWorkspaceActive: @MainActor (SavedWindowWorkspace) -> Bool
}
