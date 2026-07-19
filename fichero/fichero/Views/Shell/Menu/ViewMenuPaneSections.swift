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
                showLabel: "Show Library Browser",
                hideLabel: "Hide Library Browser",
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
                showLabel: "Show Reading Pane",
                hideLabel: "Hide Reading Pane",
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

// MARK: - Selection-driven Layout

/// Opt-in toggle for selection-driven layout changes. OFF by default so the
/// visible pane set is stable — selecting a folder vs a PDF shows the same
/// panes. ON restores the legacy behaviour where a folder collapses the
/// preview pane. App-wide @AppStorage, so a Toggle reflects external changes
/// (mirrors ShowRulerButton's rationale). (#1452)
struct SelectionDrivenLayoutToggle: View {
    @AppStorage("layout.followsSelection") private var layoutFollowsSelection: Bool = false

    var body: some View {
        Toggle(isOn: $layoutFollowsSelection) {
            Label("Selection Changes Layout", systemImage: "rectangle.on.rectangle")
        }
    }
}

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

/// App-wide toggle for the rich-text ruler. Keeps the menu checkmark in sync
/// with the persisted preference and forwards the actual toggle to the focused
/// text view when one exists.
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
            Label("Find in Artifact", systemImage: "magnifyingglass")
        }
        .keyboardShortcut("f", modifiers: [.command, .option])
        #else
        Button {
        } label: {
            Label("Find in Artifact", systemImage: "magnifyingglass")
        }
        .keyboardShortcut("f", modifiers: [.command, .option])
        .disabled(true)
        #endif
    }
}
