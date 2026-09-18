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

    /// Tabs and splits, as a SECTION of the Workspaces menu (Daniel,
    /// 2026-09-01 — it was its own toolbar item). Split now mutates the applied `PaneList`
    /// directly (#4685) rather than posting to the retired `SplittablePane`
    /// slot-id space, which never matched the applied renderer's own ids.
    @ViewBuilder
    var splitSection: some View {
        let leafID = focusedLeafID
        Section("Split") {
            Button {
                // The existing new-tab path — the same WindowOpener the
                // library rows' "Open in New Tab" uses.
                WindowOpener.open(
                    libraryId: windowState.libraryId,
                    asTab: true,
                    using: openWindow
                )
            } label: {
                Label("New Tab", systemImage: "plus.rectangle.on.rectangle")
            }
            .help("Open this library in a new tab of this window")

            Button {
                splitFocusedLeaf(.vertical)
            } label: {
                Label("Split Right", systemImage: "square.split.2x1")
            }
            .disabled(leafID == nil)
            .help(leafID == nil
                  ? "Focus a pane that can split first"
                  : "Split the focused pane side by side")

            Button {
                splitFocusedLeaf(.horizontal)
            } label: {
                Label("Split Below", systemImage: "square.split.1x2")
            }
            .disabled(leafID == nil)
            .help(leafID == nil
                  ? "Focus a pane that can split first"
                  : "Split the focused pane top and bottom")
        }
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
        Menu {
            workspaceLayoutsSection
            splitSection
            savedWorkspaceSection
            Divider()
            Button("Save Current as Workspace…") {
                chromeUX.workspaceNameDraft = ""
                chromeUX.showSaveWorkspacePrompt = true
            }
            .help("Name the current arrangement — panes, widths, splits, the "
                + "workflow and markup bars, and toolbar buttons — so you can "
                + "come back to it")
            deleteWorkspaceMenu
            Divider()
            toolbarButtonsMenu
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

    /// The v2 PaneList-backed workspaces — the ONE built-in workspace system (spec
    /// workspaces.one-system). Applying one stores it as the window's pane list (`activePaneList`),
    /// which the centre renders directly. There is no "Default Layout" escape hatch any more: a
    /// window is ALWAYS a workspace (seeded to Read), so there is no legacy visibility layout to
    /// fall back to (CD 2026-09-16). ⌘⌥1–5 are bound in the menu bar (`WorkspaceCommandsSection`);
    /// this toolbar menu shows the same set without duplicating the keys.
    @ViewBuilder
    private var workspaceLayoutsSection: some View {
        Section("Workspaces") {
            ForEach(BuiltInWorkspaceLayout.allCases) { layout in
                Button {
                    applyWorkspaceLayout(layout)
                } label: {
                    Label(layout.title, systemImage: layout.systemImage)
                }
                .help(layout.summary)
            }
        }
    }

    /// Apply a v2 workspace as the window's STORED pane list (spec §"v2 workspace design").
    func applyWorkspaceLayout(_ layout: BuiltInWorkspaceLayout) {
        activePaneList = layout.panes
        // Remember it for the next launch (#4686/#4687) — the funnel every `activePaneList`
        // writer ends in.
        paneListDidChange()
    }

    /// The user's own, checkmarked when the window matches what they saved.
    @ViewBuilder
    private var savedWorkspaceSection: some View {
        let saved = WindowWorkspaceStore.shared.catalog.workspaces
        if !saved.isEmpty {
            let panes = currentPaneVisibilityPlan
            let toolbar = WindowWorkspaceStore.shared.toolbarVisibility
            Section("Saved") {
                ForEach(saved) { workspace in
                    Button {
                        applyLayoutSnapshot(workspace.layout)
                    } label: {
                        // Every row carries a glyph (Daniel, 2026-09-02: "add
                        // icons to the menu rows") — derived from what the
                        // arrangement IS, so it cannot go stale on a re-save.
                        // The checkmark still wins when the window matches:
                        // "you are here" outranks "this is what it looks like".
                        Label(
                            workspace.name,
                            systemImage: isActive(workspace, panes: panes, toolbar: toolbar)
                                ? "checkmark"
                                : workspace.systemImage
                        )
                    }
                    .help(workspace.help)
                }
            }
        }
    }

    @ViewBuilder
    private var deleteWorkspaceMenu: some View {
        let saved = WindowWorkspaceStore.shared.catalog.workspaces
        if !saved.isEmpty {
            Menu("Delete Workspace") {
                ForEach(saved) { workspace in
                    Button(role: .destructive) {
                        WindowWorkspaceStore.shared.remove(id: workspace.id)
                    } label: {
                        Label(workspace.name, systemImage: workspace.systemImage)
                    }
                }
            }
            .help("Remove a saved arrangement. The built-in ones cannot be deleted.")
        }
    }

    /// Which optional toolbar buttons show. App-wide, the way a Mac toolbar
    /// configuration is — and never able to hide the Workspaces menu itself,
    /// which is the control that brings the others back.
    private var toolbarButtonsMenu: some View {
        let plan = WindowWorkspaceStore.shared.toolbarVisibility
        return Menu("Toolbar Buttons") {
            toolbarItemToggle("Back and Forward", \.showNavigation)
            toolbarItemToggle("Pane Toggles", \.showPaneToggles)
            // "Split and New Tab" and "Layouts" are gone from this list
            // (Daniel, 2026-09-01): they no longer name toolbar items — they
            // are sections of the menu you are standing in. The plan still
            // carries the flags so older saved workspaces decode.
            Divider()
            Button("Show All Buttons") {
                WindowWorkspaceStore.shared.setToolbarVisibility(.everything)
            }
            .disabled(plan == .everything)
            .help("Put every optional toolbar button back")
        }
        .help("Choose which buttons the window toolbar shows")
    }

    /// A checkmarked menu item rather than a `Toggle`: the same no-colour
    /// grammar the pane buttons use — the words and the checkmark carry the
    /// state, nothing changes colour.
    private func toolbarItemToggle(
        _ title: String,
        _ field: WritableKeyPath<ToolbarVisibilityPlan, Bool>
    ) -> some View {
        let store = WindowWorkspaceStore.shared
        let isOn = store.toolbarVisibility[keyPath: field]
        return Button {
            var next = store.toolbarVisibility
            next[keyPath: field] = !isOn
            store.setToolbarVisibility(next)
        } label: {
            if isOn {
                Label(title, systemImage: "checkmark")
            } else {
                Text(title)
            }
        }
        .help(isOn ? "Hide \(title) in the toolbar" : "Show \(title) in the toolbar")
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
            canSplitFocusedLeaf: focusedLeafID != nil
        )
    }
}

/// The focused window's workspace verbs, for the menu bar.
///
/// Equatable is LOAD-BEARING (the RunWorkflowOnSelectionKey lesson): a
/// non-Equatable focused value is byte-compared per body pass, always reads
/// as changed, and cascades focus invalidations. These verbs carry no state
/// of their own — any instance from the same window is interchangeable — so
/// equality is constant (`canSplitFocusedLeaf` is a snapshot read fresh every
/// time `windowLayoutCommands` is recomputed, same as every other field here).
struct WindowLayoutCommands: Equatable {
    static func == (lhs: Self, rhs: Self) -> Bool { true }

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
}
