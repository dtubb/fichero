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

    // MARK: Workspaces

    /// Save/apply/delete named window arrangements (Daniel loves Xcode's
    /// saveable workspaces). The catalog is app-wide; applying is per window.
    var workspacesMenu: some View {
        let workspaces = WindowWorkspaceStore.shared.catalog.workspaces
        return Menu {
            Button("Save Workspace…") {
                workspaceNameDraft = ""
                showSaveWorkspacePrompt = true
            }

            if !workspaces.isEmpty {
                Section("Workspaces") {
                    ForEach(workspaces) { workspace in
                        Button(workspace.name) {
                            applyLayoutSnapshot(workspace.layout)
                        }
                    }
                }
                Menu("Delete Workspace") {
                    ForEach(workspaces) { workspace in
                        Button(workspace.name, role: .destructive) {
                            WindowWorkspaceStore.shared.remove(id: workspace.id)
                        }
                    }
                }
            }
        } label: {
            Label("Workspaces", systemImage: "rectangle.grid.1x2")
        }
        .help("Save this window arrangement, or apply a saved one")
        .accessibilityLabel("Workspaces")
        .alert("Save Workspace", isPresented: $showSaveWorkspacePrompt) {
            TextField("Name", text: $workspaceNameDraft)
            Button("Save") {
                WindowWorkspaceStore.shared.save(
                    name: workspaceNameDraft,
                    layout: captureLayoutSnapshot()
                )
            }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("Names the current pane arrangement so you can apply it later.")
        }
    }

    // MARK: Views chooser

    /// The compound layouts (Xcode's "Editor Only / Canvas / Assistant"
    /// idiom): checkmarked presets built from the pane set, saved workspaces
    /// beneath a divider.
    var viewsChooserMenu: some View {
        let current = currentPaneVisibilityPlan
        let workspaces = WindowWorkspaceStore.shared.catalog.workspaces
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
            if !workspaces.isEmpty {
                Divider()
                ForEach(workspaces) { workspace in
                    Button(workspace.name) {
                        applyLayoutSnapshot(workspace.layout)
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
            layoutMode: currentLayoutMode.rawValue
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
        }
        paneSplitCoordinator.applySplits(snapshot.splits)
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
                workspaceNameDraft = ""
                showSaveWorkspacePrompt = true
            },
            applyWorkspace: { applyLayoutSnapshot($0.layout) },
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
    let applyPreset: @MainActor (WindowLayoutPreset) -> Void
}
