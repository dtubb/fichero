import SwiftUI

// MARK: - Inspector Button

/// Inspector show/hide command.
/// Reads/writes the focused window's inspector visibility via FocusedValues so
/// the toggle is per-window, not app-wide (#1451). Defaults to "Show" when no
/// window is focused (e.g. the command is evaluated with no key window).
struct InspectorButton: View {
    @FocusedValue(\.showInspector) var showInspector

    private var isVisible: Bool {
        showInspector?.wrappedValue ?? false
    }

    var body: some View {
        Button {
            showInspector?.wrappedValue.toggle()
        } label: {
            Label(
                isVisible ? "Hide Inspector" : "Show Inspector",
                systemImage: "sidebar.right"
            )
        }
        .keyboardShortcut("i", modifiers: [.command, .control])
        .disabled(showInspector == nil)
    }
}

// MARK: - Pane Visibility Section

/// View-menu items that mirror the reading-surface pane toggles already present
/// as toolbar buttons (#1215). Each reads the focused window's pane-visibility
/// binding via FocusedValues so the command is per-window (same rationale as
/// `InspectorButton`) and stays in sync with the toolbar. A binding is only
/// published while its window is focused, so each item disables when no
/// reading-capable window is key.
struct PaneVisibilitySection: View {
    @FocusedValue(\.showDocumentGrid) private var showDocumentGrid
    @FocusedValue(\.showDocumentCanvas) private var showDocumentCanvas
    @FocusedValue(\.showReadingPane) private var showReadingPane

    var body: some View {
        Section("Panes") {
            PaneToggleButton(
                binding: showDocumentGrid,
                showLabel: "Show Library",
                hideLabel: "Hide Library",
                icon: "books.vertical",
                shortcut: KeyboardShortcut("g", modifiers: [.command, .shift])
            )
            PaneToggleButton(
                binding: showDocumentCanvas,
                showLabel: "Show Preview",
                hideLabel: "Hide Preview",
                icon: "doc.richtext",
                shortcut: nil
            )
            PaneToggleButton(
                binding: showReadingPane,
                showLabel: "Show Reader",
                hideLabel: "Hide Reader",
                icon: "text.book.closed",
                shortcut: nil
            )
            ShowMiniToolbarToggle()
        }
    }
}

/// Reusable Show/Hide pane command. Mirrors `InspectorButton`: toggles the
/// focused window's binding and disables when no window publishes it.
struct PaneToggleButton: View {
    let binding: Binding<Bool>?
    let showLabel: String
    let hideLabel: String
    let icon: String
    let shortcut: KeyboardShortcut?

    private var isVisible: Bool {
        binding?.wrappedValue ?? false
    }

    var body: some View {
        Button {
            binding?.wrappedValue.toggle()
        } label: {
            Label(isVisible ? hideLabel : showLabel, systemImage: icon)
        }
        .keyboardShortcut(shortcut)
        .disabled(binding == nil)
    }
}

// MARK: - Workspaces (Daniel, 2026-08-29)

/// View ▸ Workspaces: the same commands as the toolbar's Workspaces and
/// Views-chooser buttons — layout presets, the saved workspaces, and Save
/// Workspace… — acting on the focused window via `windowLayoutCommands`
/// (same mechanism as `InspectorButton`). Items disable when no window
/// publishes the verbs rather than silently doing nothing.
struct WorkspaceCommandsSection: View {
    @FocusedValue(\.windowLayoutCommands) private var commands

    /// ⌘⌥N for the v2 workspace at slot N (1–5), else nil. The pure position lives on
    /// `BuiltInWorkspaceLayout.defaultSlot`; the SwiftUI shortcut is minted here. ⌘⌥7–9 stay free
    /// for user workspaces (spec §"v2 workspace design", the slot→workspace map).
    // #4902: `nonisolated` is load-bearing — MenuShortcutUniquenessTests is a
    // non-@MainActor Swift Testing suite calling this directly; pure over its
    // own parameter, no actor-isolated state read.
    nonisolated static func shortcut(for layout: BuiltInWorkspaceLayout) -> KeyboardShortcut? {
        let number = layout.defaultSlot
        guard (1...9).contains(number) else { return nil }
        return KeyboardShortcut(KeyEquivalent(Character(String(number))), modifiers: [.command, .option])
    }

    var body: some View {
        // No inner title: the parent flyout is "View ▸ Workspaces ▸", so a
        // "Workspaces" header here would read as "Workspaces ▸ Workspaces".
        // The "Layouts" section below keeps its title — it distinguishes the
        // pane-visibility presets from the workspaces above.
        Section {
            // The v2 workspaces are the ONE built-in system (spec workspaces.one-system): real 2D
            // PaneList compositions, applied to the focused window's `activePaneList` via the
            // command bus. ⌘⌥1–5 switch between them. (The legacy `BuiltInWorkspace` show/hide
            // presets — enum, wiring and tests — are deleted; this is the one built-in system.)
            ForEach(BuiltInWorkspaceLayout.allCases) { layout in
                Button {
                    commands?.applyWorkspaceLayout(layout)
                } label: {
                    Label(layout.title, systemImage: layout.systemImage)
                }
                .keyboardShortcut(Self.shortcut(for: layout))
                .disabled(commands == nil)
            }

            ForEach(WindowWorkspaceStore.shared.catalog.workspaces) { workspace in
                Button {
                    commands?.applyWorkspace(workspace)
                } label: {
                    // Icons on every row (Daniel, 2026-09-02), and the same
                    // derived glyph the toolbar's Workspaces menu shows — one
                    // arrangement must not wear two faces in two menus.
                    Label(workspace.name, systemImage: workspace.systemImage)
                }
                .help(workspace.help)
                .disabled(commands == nil)
            }

            Button("Save Workspace…") {
                commands?.saveWorkspace()
            }
            .disabled(commands == nil)
        }
        // The legacy "Layouts" preset section (WindowLayoutPreset) is gone (CD 2026-09-16): a
        // workspace IS the layout, so showing pane-visibility presets beside the workspaces was the
        // "why are layouts different from workspaces" duplication (spec workspaces.one-system).

        // Split / New Tab (#4685 addendum): previously reachable ONLY from the toolbar's
        // Workspaces menu, not the menu bar — given a home here now that Split routes through
        // the `PaneList` model instead of the dead slot-id space.
        Section("Split") {
            Button {
                commands?.newTab()
            } label: {
                Label("New Tab", systemImage: "plus.rectangle.on.rectangle")
            }
            .disabled(commands == nil)

            Button {
                commands?.splitFocusedLeaf(.vertical)
            } label: {
                Label("Split Right", systemImage: "square.split.2x1")
            }
            .disabled(commands?.canSplitFocusedLeaf != true)

            Button {
                commands?.splitFocusedLeaf(.horizontal)
            } label: {
                Label("Split Below", systemImage: "square.split.1x2")
            }
            .disabled(commands?.canSplitFocusedLeaf != true)
        }
    }
}

// MARK: - Selection-driven Layout

// Opt-in toggle for selection-driven layout changes. OFF by default so the
// visible pane set is stable — selecting a folder vs a PDF shows the same
// panes. ON restores the legacy behaviour where a folder collapses the
// preview pane. App-wide @AppStorage; the toggle now lives in Settings ▸
// General (#4121) — SelectionDrivenLayoutToggle deleted with the move.

// MARK: - Show Mini Toolbar (#2460)

/// App-wide toggle for reader mini-toolbars. Toggle in a CommandMenu renders as
/// a checkmark item that stays in sync with @AppStorage changes from any window
/// (same rationale as ShowRulerButton). Key must match MiniToolbar.toolbarVisibilityKey.
struct ShowMiniToolbarToggle: View {
    @AppStorage(
        wrappedValue: MiniToolbarPreferences.toolbarVisibilityDefault,
        MiniToolbarPreferences.toolbarVisibilityKey
    )
    private var showMiniToolbar: Bool

    var body: some View {
        Toggle(isOn: $showMiniToolbar) {
            Label("Show Mini Toolbar", systemImage: "rectangle.topthird.inset.filled")
        }
    }
}

// MARK: - Go Up (Cmd+`)

// Walks one level up the folder hierarchy via the focused window's
// navigateToParent action. Lets users ascend when the sidebar is hidden,
// since there's no other way to climb back out of a folder. (#786)
struct NavigateToParentButton: View {
    @FocusedValue(\.navigateToParentAction) private var action

    var body: some View {
        Button {
            action?.run()
        } label: {
            Label("Go Up", systemImage: "arrow.up.to.line.compact")
        }
        .keyboardShortcut("`", modifiers: [.command])
        .disabled(action == nil)
    }
}

/// Go menu (#4121, HIG: Finder's Go/View split): pure navigation commands —
/// Back/Forward (per-window AppNavigation history, #3581) and Go Up (⌘`) —
/// out of the overfull View menu. Composed as ONE Commands element (the app
/// CommandsBuilder is at its arity cap, #3347); the empty `.sidebar`
/// replacement keeps the system sidebar items suppressed as before.
struct GoMenuCommands: Commands {
    var body: some Commands {
        CommandGroup(replacing: .sidebar) {}
        CommandMenu("Go") {
            NavigateBackButton()
            NavigateForwardButton()
            Divider()
            NavigateToParentButton()
        }
        // Help-menu manual link (Daniel, 2026-09-03: "add to help menu link
        // to user manual"). It rides in this composed element because the app
        // CommandsBuilder is at its arity cap (#3347) — a standalone
        // `CommandGroup(after: .help)` in FicheroApp would be the 11th entry.
        CommandGroup(after: .help) {
            Link("Fichero User Manual", destination: URL(string: "https://tubb.ca/apps/fichero/")!)
        }
    }
}

/// Format menu = the system text-formatting commands + Show Ruler (#4121:
/// the ruler is text-formatting chrome, not view state). Composed as ONE
/// Commands element so FicheroApp's CommandsBuilder stays under its arity cap.
struct FormatMenuCommands: Commands {
    var body: some Commands {
        TextFormattingCommands()
        CommandGroup(after: .textFormatting) {
            Divider()
            ShowRulerButton()
        }
    }
}

struct ShowRulerButton: View {
    @AppStorage("editor.rulersVisible") private var rulersVisible: Bool = true

    private var binding: Binding<Bool> {
        Binding(
            get: { rulersVisible },
            set: { newValue in
                rulersVisible = newValue
                #if canImport(AppKit)
                NSApp.sendAction(#selector(NSTextView.toggleRuler(_:)), to: nil, from: nil)
                #endif
            }
        )
    }

    var body: some View {
        Toggle(isOn: binding) {
            Label("Show Ruler", systemImage: "ruler")
        }
    }
}

/// Triggers the focused text view's inline find bar. Targets the first
/// responder via `performFindPanelAction(_:)`, which SwiftUI's `TextEditor`
/// (AppKit-backed on macOS) handles — no app-wide search. (#2453: the editor
/// is now SwiftUI `TextEditor`, not a custom NSTextView representable.)
struct ShowFindBarButton: View {
    var body: some View {
        #if canImport(AppKit)
        Button {
            let item = NSMenuItem()
            item.tag = Int(NSFindPanelAction.showFindPanel.rawValue)
            NSApp.sendAction(
                #selector(NSTextView.performFindPanelAction(_:)),
                to: nil,
                from: item
            )
        } label: {
            Label("Find in Page", systemImage: "magnifyingglass")
        }
        .keyboardShortcut("f", modifiers: [.command, .option])
        #else
        Button {
        } label: {
            Label("Find in Page", systemImage: "magnifyingglass")
        }
        .keyboardShortcut("f", modifiers: [.command, .option])
        .disabled(true)
        #endif
    }
}

// MARK: - Capability bar

/// View ▸ Show/Hide Workflow Bar (2026-08-28) — the Preview convention, where
/// a bar of verbs is opt-in chrome you switch on per window.
///
/// Reads the focused window's binding so it toggles only that window, the same
/// mechanism as Show/Hide Inspector. Disabled when no window publishes one,
/// rather than silently doing nothing.
struct ShowWorkflowBarButton: View {
    @FocusedValue(\.showWorkflowBar) private var showWorkflowBar

    var body: some View {
        Button {
            showWorkflowBar?.wrappedValue.toggle()
        } label: {
            Label(
                showWorkflowBar?.wrappedValue == true
                    ? "Hide Workflow Bar"
                    : "Show Workflow Bar",
                systemImage: "square.grid.2x2"
            )
        }
        .keyboardShortcut("w", modifiers: [.command, .option, .shift])
        .disabled(showWorkflowBar == nil)
    }
}

/// View ▸ Workflow Bar Labels — the names under the glyphs are optional
/// (Daniel, 2026-08-28): on while the vocabulary is unfamiliar, off for a
/// dense icon rail once it is not.
struct ShowWorkflowBarLabelsButton: View {
    @FocusedValue(\.showWorkflowBarLabels) private var showLabels
    @FocusedValue(\.showWorkflowBar) private var showBar

    var body: some View {
        Button {
            showLabels?.wrappedValue.toggle()
        } label: {
            Label(
                showLabels?.wrappedValue == true
                    ? "Hide Workflow Bar Labels"
                    : "Show Workflow Bar Labels",
                systemImage: "textformat.size.smaller"
            )
        }
        // Meaningless while the bar is hidden — disabled rather than silently
        // toggling something the user cannot see.
        .disabled(showLabels == nil || showBar?.wrappedValue != true)
    }
}
