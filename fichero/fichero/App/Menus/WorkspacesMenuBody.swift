import SwiftUI

// MARK: - The ONE Workspaces menu definition (#4968)

/// Everything the View menu's "Workspaces ▸" flyout and the toolbar's Workspaces menu show —
/// built-in layouts, saved workspaces, Save, Split, and the Toolbar Buttons submenu — defined
/// ONCE and rendered by both, so they cannot drift into two different lists the way #4968 found
/// them (different wording, shortcuts in only one, Split enabled in one and not the other, no
/// checkmark on the active saved workspace in one).
///
/// `commands` is the ONE per-window verb bundle (`WindowLayoutCommands`) both call sites already
/// had: the View menu receives its copy via `@FocusedValue` (a Commands scene has no other way to
/// reach the key window), the toolbar constructs its own directly from `self`. Passing it in as a
/// value, rather than reading it here, keeps this view itself dumb and reusable in either context
/// — nothing here cares HOW its caller obtained the commands.
///
/// Everything that does NOT need to be scoped to a specific window (the built-in layout list, the
/// saved-workspace catalog, and the app-wide toolbar-button visibility plan) reads its shared
/// singleton directly, same as both menus already did before this — not threaded through
/// `commands`, since neither is per-window state.
struct WorkspacesMenuBody: View {
    let commands: WindowLayoutCommands?

    var body: some View {
        // No section title here: both callers already say "Workspaces" —
        // the View menu's own "Workspaces ▸" flyout and the toolbar
        // button's own "Workspaces" label — so a header here would read as
        // "Workspaces ▸ Workspaces" in one of the two (#4968: identical
        // wording in both means picking ONE answer, not each keeping its
        // own).
        Section {
            ForEach(BuiltInWorkspaceLayout.allCases) { layout in
                Button {
                    commands?.applyWorkspaceLayout(layout)
                } label: {
                    // #4968: macOS resolves a Label's style to title-only by default inside
                    // Menu/CommandMenu content — `.titleAndIcon` must be explicit, which is why
                    // neither menu showed a glyph despite both already passing `systemImage:`.
                    // Documented, not yet confirmed on screen (`menu-label-drops-frame-modifiers`
                    // covers a related but distinct case — a Menu's own TRIGGER label dropping a
                    // bitmap image's frame; this is the default label STYLE inside menu content).
                    Label(layout.title, systemImage: layout.systemImage)
                        .labelStyle(.titleAndIcon)
                }
                .help(layout.summary)
                // ⌘⌥N for the v2 workspace at slot N (1–5) — kept on
                // `WorkspaceCommandsSection` (not moved here) because
                // `MenuShortcutUniquenessTests` calls it there by name; this
                // view just reuses it, so it displays and works identically
                // in both menus rather than being minted twice.
                .keyboardShortcut(WorkspaceCommandsSection.shortcut(for: layout))
                .disabled(commands == nil)
            }
        }

        if !WindowWorkspaceStore.shared.catalog.workspaces.isEmpty {
            Section("Saved") {
                ForEach(WindowWorkspaceStore.shared.catalog.workspaces) { workspace in
                    Button {
                        commands?.applyWorkspace(workspace)
                    } label: {
                        // The checkmark still wins when the window matches: "you are here"
                        // outranks "this is what it looks like" (unchanged from the toolbar's
                        // prior-only behavior — now shown identically in both menus).
                        Label(
                            workspace.name,
                            systemImage: (commands?.isWorkspaceActive(workspace) ?? false)
                                ? "checkmark" : workspace.systemImage
                        )
                        .labelStyle(.titleAndIcon)
                    }
                    .help(workspace.help)
                    .disabled(commands == nil)
                }
            }
        }

        Divider()

        Button("Save Workspace…") {
            commands?.saveWorkspace()
        }
        .disabled(commands == nil)

        if !WindowWorkspaceStore.shared.catalog.workspaces.isEmpty {
            Menu("Delete Workspace") {
                ForEach(WindowWorkspaceStore.shared.catalog.workspaces) { workspace in
                    Button(role: .destructive) {
                        WindowWorkspaceStore.shared.remove(id: workspace.id)
                    } label: {
                        Label(workspace.name, systemImage: workspace.systemImage)
                            .labelStyle(.titleAndIcon)
                    }
                }
            }
            .help("Remove a saved arrangement. The built-in ones cannot be deleted.")
        }

        Divider()

        Section("Split") {
            Button {
                commands?.newTab()
            } label: {
                Label("New Tab", systemImage: "plus.rectangle.on.rectangle")
                    .labelStyle(.titleAndIcon)
            }
            .help("Open this library in a new tab of this window")
            .disabled(commands == nil)

            Button {
                commands?.splitFocusedLeaf(.vertical)
            } label: {
                Label(splitTitle(axis: .vertical), systemImage: "square.split.2x1")
                    .labelStyle(.titleAndIcon)
            }
            .help(splitHelp(axis: .vertical))
            .disabled(commands?.canSplitFocusedLeaf != true)

            Button {
                commands?.splitFocusedLeaf(.horizontal)
            } label: {
                Label(splitTitle(axis: .horizontal), systemImage: "square.split.1x2")
                    .labelStyle(.titleAndIcon)
            }
            .help(splitHelp(axis: .horizontal))
            .disabled(commands?.canSplitFocusedLeaf != true)
        }

        Divider()

        toolbarButtonsMenu
    }

    /// #4968: names WHICH pane a Split command acts on, using the focused pane's kind when the
    /// window makes it cheaply available (`WindowLayoutCommands.focusedPaneKindForSplit`) — a
    /// bare "Split Right" never said what it split or what would appear in the new half.
    private func splitTitle(axis: SplitAxis) -> String {
        let direction = axis == .vertical ? "Right" : "Below"
        guard let kind = commands?.focusedPaneKindForSplit else {
            return "Split Focused Pane \(direction)"
        }
        return "Split \(Self.title(for: kind)) \(direction)"
    }

    private func splitHelp(axis: SplitAxis) -> String {
        guard commands?.canSplitFocusedLeaf == true else {
            return "Focus a pane that can split first"
        }
        let orientation = axis == .vertical ? "side by side" : "top and bottom"
        if let kind = commands?.focusedPaneKindForSplit {
            return "Split the focused \(Self.title(for: kind)) pane \(orientation)"
        }
        return "Split the focused pane \(orientation)"
    }

    /// `PaneKind` (`Models/PaneList.swift`) is a pure model type with no display strings of its
    /// own — this mirrors `PaneSpec.Kind.title`'s wording (the view-layer twin the model type's
    /// own doc comment says it mirrors) without adding a dependency on that file.
    private static func title(for kind: PaneKind) -> String {
        switch kind {
        case .library: "Library"
        case .preview: "Preview"
        case .reading: "Reader"
        case .inspector: "Inspector"
        case .chat: "Chat"
        }
    }

    /// #4968: real and kept, given a clearer sense of scope in its help text — this toggles which
    /// OPTIONAL toolbar buttons show (`ToolbarVisibilityPlan.showNavigation`/`.showPaneToggles`,
    /// read at `ContentView+Toolbar.swift:62` and `:167`), an app-wide setting
    /// (`WindowWorkspaceStore.shared.toolbarVisibility`), not a per-window one — which is why it
    /// needs no `commands` at all and can never be "disabled" by a lack of window focus.
    private var toolbarButtonsMenu: some View {
        let plan = WindowWorkspaceStore.shared.toolbarVisibility
        return Menu("Toolbar Buttons") {
            toolbarItemToggle("Back and Forward", \.showNavigation)
            toolbarItemToggle("Pane Toggles", \.showPaneToggles)
            Divider()
            Button("Show All Buttons") {
                WindowWorkspaceStore.shared.setToolbarVisibility(.everything)
            }
            .disabled(plan == .everything)
            .help("Put every optional toolbar button back")
        }
        .help("Choose which optional buttons the window's toolbar shows")
    }

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
                    .labelStyle(.titleAndIcon)
            } else {
                Text(title)
            }
        }
        .help(isOn ? "Hide \(title) in the toolbar" : "Show \(title) in the toolbar")
    }
}
