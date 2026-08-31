import SwiftUI

// MARK: - Split/Tab, Workspaces, and Views chooser (Daniel, 2026-08-29)
//
// Xcode 27's window chrome is the explicit model: one toolbar button unifies
// New Tab + pane splitting (the ⊞+ idiom), one saves/applies named
// workspaces, and one offers the compound layouts. Small named subviews per
// the type-checker budget; policy (serialisation, presets, split routing)
// lives in WindowWorkspace.swift as pure testable types.

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

    /// ONE entry point to tabs and splits (Daniel, 2026-08-29: some panes
    /// offered splits and chat did not — this button splits whichever pane
    /// has focus, chat included, through the existing SplittablePane
    /// machinery). "Split Right"/"Split Below" CYCLE the axis the way the
    /// pane-head buttons always have (1 → 2 → 3 → 1).
    var splitAndTabMenu: some View {
        let splitKey = focusedSplitStorageKey
        return Menu {
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

            Divider()

            Button {
                requestFocusedPaneSplit(.vertical)
            } label: {
                Label("Split Right", systemImage: "square.split.2x1")
            }
            .disabled(splitKey == nil)

            Button {
                requestFocusedPaneSplit(.horizontal)
            } label: {
                Label("Split Below", systemImage: "square.split.1x2")
            }
            .disabled(splitKey == nil)
        } label: {
            Label("Split", systemImage: "square.split.2x1")
        }
        .help("Open a new tab, or split the focused pane")
        .accessibilityLabel("New tab and split options")
    }

    private func requestFocusedPaneSplit(_ axis: SplitPaneAxis) {
        guard let key = focusedSplitStorageKey else { return }
        paneSplitCoordinator.requestSplit(storageKey: key, axis: axis)
    }

    // MARK: Workspaces (ONE button — Daniel, 2026-08-31)

    /// The single workspaces control. It used to be TWO: this menu (save /
    /// apply / delete) and the Views chooser, which listed every saved
    /// workspace a second time beneath its presets. "Combine them all into
    /// ONE button" — so the saved list lives here, alone, and the Views
    /// chooser goes back to being purely about showing and hiding views.
    ///
    /// A workspace now carries the TOOLBAR too: which optional buttons show,
    /// and whether the workflow bar rides along. Three built-in arrangements
    /// ship with the app so the menu is useful before anything is saved.
    var workspacesMenu: some View {
        Menu {
            builtInWorkspaceSection
            savedWorkspaceSection
            Divider()
            Button("Save Current as Workspace…") {
                chromeUX.workspaceNameDraft = ""
                chromeUX.showSaveWorkspacePrompt = true
            }
            deleteWorkspaceMenu
            Divider()
            toolbarButtonsMenu
        } label: {
            Label("Workspaces", systemImage: "rectangle.grid.1x2")
        }
        .help("Apply, save, or delete a window arrangement — panes, workflow "
            + "bar, and toolbar buttons")
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
            Text("Names this arrangement — panes, widths, workflow bar, and "
                + "toolbar buttons — so you can apply it later.")
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
                        panes: panes, toolbar: toolbar, workflowBar: showWorkflowBar
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
                        if isActive(workspace, panes: panes, toolbar: toolbar) {
                            Label(workspace.name, systemImage: "checkmark")
                        } else {
                            Text(workspace.name)
                        }
                    }
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
                    Button(workspace.name, role: .destructive) {
                        WindowWorkspaceStore.shared.remove(id: workspace.id)
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
            toolbarItemToggle("Split and New Tab", \.showSplitMenu)
            toolbarItemToggle("Layouts", \.showLayoutsMenu)
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
    }

    // MARK: Views chooser

    /// The compound layouts (Xcode's "Editor Only / Canvas / Assistant"
    /// idiom): checkmarked presets built from the pane set.
    ///
    /// The saved-workspace list that used to hang beneath these is GONE
    /// (Daniel, 2026-08-31) — it was the second workspace control. This
    /// button is now only what its help says: which views the window shows.
    var viewsChooserMenu: some View {
        let current = currentPaneVisibilityPlan
        return Menu {
            ForEach(WindowLayoutPreset.allCases) { preset in
                Button {
                    applyLayoutPreset(preset)
                } label: {
                    if preset.matches(current) {
                        Label(preset.title, systemImage: "checkmark")
                    } else {
                        Text(preset.title)
                    }
                }
            }
        } label: {
            Label("Layouts", systemImage: "squares.leading.rectangle")
        }
        .help("Choose which panes this window shows")
        .accessibilityLabel("Layout chooser")
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
            showWorkflowBar: showWorkflowBar
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
        }
        paneSplitCoordinator.applySplits(snapshot.splits)
        // Toolbar last, and outside the animation: it is app-wide chrome, not
        // this window's geometry, and re-laying the NSToolbar mid-animation is
        // exactly the kind of churn #3163 taught us to keep off the critical
        // path.
        WindowWorkspaceStore.shared.setToolbarVisibility(snapshot.toolbar)
    }

    /// Applies one of the built-in arrangements. It touches ONLY what a
    /// built-in can honestly know — panes, workflow bar, toolbar buttons —
    /// leaving widths, splits, kind overrides and the view mode as the user
    /// has them.
    func applyBuiltInWorkspace(_ workspace: BuiltInWorkspace) {
        withAnimation(FrameAnimation.snappy) {
            applyPaneVisibilityPlan(workspace.panes)
            showWorkflowBar = workspace.showsWorkflowBar
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
