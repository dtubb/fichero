import SwiftUI

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

    /// The focused pane's SplittablePane storage key, or nil when focus is on
    /// a surface that does not split (sidebar/inspector) or outside the row.
    var focusedSplitStorageKey: String? {
        SplitCommandRouting.storageKey(
            focus: focusedPane ?? paneFocusHint,
            slots: widescreenPaneSpecs.map { ($0.id, $0.kind.rawValue) },
            overrides: paneKindOverrides.mapValues(\.rawValue)
        )
    }

    /// Tabs and splits, as a SECTION of the Workspaces menu (Daniel,
    /// 2026-09-01 — it was its own toolbar item). "Split Right"/"Split Below"
    /// CYCLE the axis the way the pane-head buttons always have (1 → 2 → 3 →
    /// 1), and they split whichever pane has focus, chat included, through the
    /// existing SplittablePane machinery.
    @ViewBuilder
    var splitSection: some View {
        let splitKey = focusedSplitStorageKey
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
                requestFocusedPaneSplit(.vertical)
            } label: {
                Label("Split Right", systemImage: "square.split.2x1")
            }
            .disabled(splitKey == nil)
            .help(splitKey == nil
                  ? "Focus a pane that can split first"
                  : "Split the focused pane side by side — click again to cycle 1 → 2 → 3 panes")

            Button {
                requestFocusedPaneSplit(.horizontal)
            } label: {
                Label("Split Below", systemImage: "square.split.1x2")
            }
            .disabled(splitKey == nil)
            .help(splitKey == nil
                  ? "Focus a pane that can split first"
                  : "Split the focused pane top and bottom — click again to cycle 1 → 2 → 3 panes")
        }
    }

    private func requestFocusedPaneSplit(_ axis: SplitPaneAxis) {
        guard let key = focusedSplitStorageKey else { return }
        paneSplitCoordinator.requestSplit(storageKey: key, axis: axis)
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
            layoutsSection
            splitSection
            builtInWorkspaceSection
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

    /// The three that ship. Computed, never stored, so they cannot be
    /// deleted and choosing one again IS the reset.
    @ViewBuilder
    private var builtInWorkspaceSection: some View {
        let panes = currentPaneVisibilityPlan
        let toolbar = WindowWorkspaceStore.shared.toolbarVisibility
        Section("Default") {
            ForEach(BuiltInWorkspace.allCases) { workspace in
                Button {
                    applyBuiltInWorkspace(workspace)
                } label: {
                    if workspace.matches(
                        panes: panes, toolbar: toolbar,
                        workflowBar: showWorkflowBar, markupBar: showAnnotationBar
                    ) {
                        Label(workspace.title, systemImage: "checkmark")
                    } else {
                        Label(workspace.title, systemImage: workspace.systemImage)
                    }
                }
                .help(workspace.help)
            }
        }
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

    // MARK: Layouts

    /// The compound layouts (Xcode's "Editor Only / Canvas / Assistant"
    /// idiom): checkmarked presets built from the pane set. A SECTION now
    /// (Daniel, 2026-09-01) rather than its own toolbar item — "which views
    /// this window shows" is the first question the Workspaces menu answers.
    @ViewBuilder
    var layoutsSection: some View {
        let current = currentPaneVisibilityPlan
        Section("Layouts") {
            ForEach(WindowLayoutPreset.allCases) { preset in
                Button {
                    applyLayoutPreset(preset)
                } label: {
                    Label(preset.title,
                          systemImage: preset.matches(current)
                              ? "checkmark" : preset.systemImage)
                }
                .help("Show the \(preset.title) arrangement of panes")
            }
        }
    }

    // MARK: Capture / apply

    var currentPaneVisibilityPlan: PaneVisibilityPlan {
        PaneVisibilityPlan(
            showSidebar: showSidebar,
            showInspector: showInspectorSidebar,
            showLibraryPane: showDocumentGrid,
            showPreviewPane: showDocumentCanvas,
            showReaderPane: showReadingPane,
            showChatPane: showChatPane
        )
    }

    func captureLayoutSnapshot() -> WindowLayoutSnapshot {
        WindowLayoutSnapshot(
            panes: currentPaneVisibilityPlan,
            libraryPaneWidth: widescreenContentPaneWidth,
            readerPaneWidth: pageContentPaneWidth,
            chatPaneWidth: chatPaneWidth,
            paneKindOverrides: paneKindOverrides.mapValues(\.rawValue),
            splits: paneSplitCoordinator.splitCounts,
            viewDisplayMode: viewDisplayMode.rawValue,
            layoutMode: currentLayoutMode.rawValue,
            toolbar: WindowWorkspaceStore.shared.toolbarVisibility,
            showWorkflowBar: showWorkflowBar,
            showAnnotationBar: showAnnotationBar
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
            paneKindOverrides = snapshot.paneKindOverrides
                .compactMapValues(PaneSpec.Kind.init(rawValue:))
            if let mode = LayoutMode(rawValue: snapshot.layoutMode) {
                updateLayoutMode(mode)
            }
            if let display = ViewDisplayMode(rawValue: snapshot.viewDisplayMode) {
                updateViewDisplayMode(display)
            }
            showWorkflowBar = snapshot.showWorkflowBar
            showAnnotationBar = snapshot.showAnnotationBar
        }
        paneSplitCoordinator.applySplits(snapshot.splits)
        // Toolbar last, and outside the animation: it is app-wide chrome, not
        // this window's geometry, and re-laying the NSToolbar mid-animation is
        // exactly the kind of churn #3163 taught us to keep off the critical
        // path.
        WindowWorkspaceStore.shared.setToolbarVisibility(snapshot.toolbar)
    }

    /// Applies one of the built-in arrangements. It touches ONLY what a
    /// built-in can honestly know — panes, both window bars, toolbar buttons
    /// — leaving widths, splits, kind overrides and the view mode as the user
    /// has them.
    func applyBuiltInWorkspace(_ workspace: BuiltInWorkspace) {
        withAnimation(FrameAnimation.snappy) {
            applyPaneVisibilityPlan(workspace.panes)
            showWorkflowBar = workspace.showsWorkflowBar
            showAnnotationBar = workspace.showsMarkupBar
        }
        WindowWorkspaceStore.shared.setToolbarVisibility(workspace.toolbar)
    }

    /// A preset touches ONLY pane visibility — widths, kind overrides and
    /// splits stay as the user has them.
    func applyLayoutPreset(_ preset: WindowLayoutPreset) {
        withAnimation(FrameAnimation.snappy) {
            applyPaneVisibilityPlan(preset.plan)
        }
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
            applyBuiltIn: { applyBuiltInWorkspace($0) },
            applyPreset: { applyLayoutPreset($0) }
        )
    }
}

/// The focused window's workspace verbs, for the menu bar.
///
/// Equatable is LOAD-BEARING (the RunWorkflowOnSelectionKey lesson): a
/// non-Equatable focused value is byte-compared per body pass, always reads
/// as changed, and cascades focus invalidations. These verbs carry no state
/// of their own — any instance from the same window is interchangeable — so
/// equality is constant.
struct WindowLayoutCommands: Equatable {
    static func == (lhs: Self, rhs: Self) -> Bool { true }

    let saveWorkspace: @MainActor () -> Void
    let applyWorkspace: @MainActor (SavedWindowWorkspace) -> Void
    let applyBuiltIn: @MainActor (BuiltInWorkspace) -> Void
    let applyPreset: @MainActor (WindowLayoutPreset) -> Void
}
