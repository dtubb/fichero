import SwiftUI

// MARK: - Sort Section

/// Sort By and direction commands for the library/search content area
/// Only shown for Library and Search modes; reads/writes LibraryView sort state via FocusedValues
struct SortSection: View {
    @FocusedValue(\.sidebarMode) var sidebarMode
    @FocusedValue(\.librarySortField) var sortField
    @FocusedValue(\.librarySortAscending) var sortAscending

    private var shouldShow: Bool {
        sidebarMode?.wrappedValue == .library
    }

    var body: some View {
        if shouldShow {
            // No inner title: the parent flyout is "View ▸ Sort ▸", so a
            // "Sort By" header here would read as "Sort ▸ Sort By".
            Section {
                // The focused value carries the search context now, so this
                // menu offers Relevance exactly when the toolbar's does — and
                // never over a browsed folder, where it would name a ranking
                // that does not exist.
                ForEach(LibrarySortField.fields(isSearching: sortField?.isSearching ?? false)) { field in
                    Button {
                        sortField?.set(field.rawValue)
                    } label: {
                        Label(field.rawValue, systemImage: field.icon)
                        if sortField?.value == field.rawValue {
                            Image(systemName: "checkmark")
                        }
                    }
                }

                Divider()

                Button {
                    sortAscending?.set(true)
                } label: {
                    Text("Ascending")
                    if sortAscending?.value == true {
                        Image(systemName: "checkmark")
                    }
                }

                Button {
                    sortAscending?.set(false)
                } label: {
                    Text("Descending")
                    if sortAscending?.value == false {
                        Image(systemName: "checkmark")
                    }
                }
            }
        }
    }
}

// MARK: - Preview Mode Section

/// Preview mode selection commands (None, Standard, Widescreen)
/// Only shown for modes with preview panes (Library, Search, Chat)
struct PreviewModeSection: View {
    @Bindable var viewSettings: ViewSettings
    let featureManager = FeatureManager.shared
    @FocusedValue(\.sidebarMode) var sidebarMode

    /// Only show preview options for modes that have preview panes
    private var shouldShowPreviewOptions: Bool {
        availablePreviewModes.count > 1
    }

    private var availablePreviewModes: [PreviewMode] {
        guard let mode = sidebarMode?.wrappedValue else { return [] }
        switch mode {
        case .library:
            if !featureManager.isLibrarySearchSplitLayoutsEnabled {
                return [.standard]
            }
            return [.none, .standard, .widescreen]
        case .chat:
            return [.none, .standard, .widescreen]
        case .workflows, .automation, .activity, .research:
            return []
        }
    }

    var body: some View {
        if shouldShowPreviewOptions {
            // Preview LAYOUT — where the document preview sits relative to the
            // library list. Mail-modeled radio group (#2032/§6d):
            //   .widescreen → list and preview side-by-side  → "Show Side Preview"
            //   .standard   → list above, preview below       → "Show Bottom Preview"
            //   .none       → list only, no preview           → "Hide Preview"
            // (This is the PREVIEW position; the list's own column layout —
            // Icons/List/Table/Canvas/Space/Columns — is LibraryLayoutSection
            // ⌘1-6, not here.)
            //
            // Shortcuts are ⌃⌘ + letter (Daniel, 2026-09-05), NOT ⌘-numbers:
            // the layout section already owns ⌘1-6, and both sections render in
            // Library/Search mode, so ⌘5/⌘6 meant BOTH "as Space"/"as Columns"
            // AND "Show Side"/"Show Bottom" — a live collision. ⌃⌘ is the pane
            // family (the inspector toggle is ⌃⌘I); sidebar MODES take ⌃⌘
            // NUMBERS, so ⌃⌘ letters here don't collide with those either.
            // No inner title: the parent flyout is "View ▸ Preview ▸", so a
            // "Preview" header here would read as "Preview ▸ Preview".
            //
            // Menu audit 2026-09-17: "Show Side Preview" was ⌃⌘S — the macOS
            // HIG chord for Show/Hide Sidebar, which this app has no command
            // for at all (`toggleSidebar()` in ContentView+ActionsUI.swift has
            // zero callers). Freed to ⌃⌘J so a future Show/Hide Sidebar
            // command can claim ⌃⌘S; see MenuShortcutUniquenessTests' denylist,
            // which blocks ⌃⌘S until that command exists.
            Section {
                if availablePreviewModes.contains(.widescreen) {
                    PreviewModeButton(
                        mode: .widescreen,
                        label: "Show Side Preview",
                        icon: "rectangle.split.2x1",
                        shortcut: "j",
                        current: viewSettings.previewMode
                    ) {
                        viewSettings.previewMode = .widescreen
                    }
                }

                if availablePreviewModes.contains(.standard) {
                    PreviewModeButton(
                        mode: .standard,
                        label: "Show Bottom Preview",
                        icon: "rectangle.split.1x2",
                        shortcut: "b",
                        current: viewSettings.previewMode
                    ) {
                        viewSettings.previewMode = .standard
                    }
                }

                if availablePreviewModes.contains(.none) {
                    PreviewModeButton(
                        mode: .none,
                        label: "Hide Preview",
                        icon: "square",
                        shortcut: "h",
                        current: viewSettings.previewMode
                    ) {
                        viewSettings.previewMode = .none
                    }
                }
            }
        }
    }
}

/// Reusable preview mode button with checkmark when active
struct PreviewModeButton: View {
    let mode: PreviewMode
    let label: String
    let icon: String
    let shortcut: String
    let current: PreviewMode
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if current == mode {
                    Image(systemName: "checkmark")
                        .frame(width: 12)
                }
                Image(systemName: icon)
                    .frame(width: 16)
                Text(label)
            }
        }
        // ⌃⌘ (control+command), NOT plain ⌘: the plain ⌘-number range belongs to
        // the library layouts (⌘1-6), which render in the same mode — see the
        // collision note in PreviewModeSection.
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.command, .control]
        )
    }
}

// MARK: - Representation Section ("Add View")

/// Document content-area representation switcher, surfaced as View-menu items
/// instead of a floating icon bar over the WebKit content (#2032 / reform §G).
/// The maintainer: "the stuff shown in the WebKit/content view are really views that can
/// be ADDED — so the switcher should be MENU ITEMS, not icons." Reads/writes the
/// focused `DocumentKGSurface`'s active representation via FocusedValues, so it's
/// per-window and disables when no document surface is focused (same rationale as
/// `InspectorButton` / `PaneVisibilitySection`).
struct RepresentationSection: View {
    @FocusedValue(\.documentRepresentation) private var representation

    private var current: KGSurfaceTab? {
        representation?.current
    }

    var body: some View {
        Section("Add View") {
            ForEach(KGSurfaceTab.allCases) { tab in
                Button {
                    representation?.select(tab)
                } label: {
                    Label(tab.title, systemImage: tab.icon)
                    if current == tab {
                        Image(systemName: "checkmark")
                    }
                }
                .keyboardShortcut(
                    KeyEquivalent(tab.representationShortcut),
                    modifiers: [.control, .option, .command]
                )
                .disabled(representation == nil)
            }
        }
    }
}

// Knowledge Graph View Mode Section DELETED (#4705 increment 3): it switched
// the focused `OntologyBrowser`'s own List/Graph/Chart/Timeline/Map mode via
// FocusedValues — with `OntologyBrowser` retired there is no subject left for
// it to control. The `\.knowledgeGraphViewMode` FocusedValues entry and its
// `KnowledgeGraphViewModeFocus` wrapper (both `OntologyBrowser`-only) retire
// alongside it.
