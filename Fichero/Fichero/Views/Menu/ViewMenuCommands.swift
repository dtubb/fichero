import SwiftUI

/// View menu commands - Sidebar modes, library layouts, preview modes, and inspector toggle
/// Extracted from FicheroApp.swift to maintain consistency with other menu command patterns
struct ViewMenuCommands: View {
    @EnvironmentObject var viewSettings: ViewSettings

    var body: some View {
        SidebarModeSection(viewSettings: viewSettings)

        Divider()

        LibraryLayoutSection(viewSettings: viewSettings)

        Divider()

        PreviewModeSection(viewSettings: viewSettings)

        Divider()

        QuickLookButton(viewSettings: viewSettings)

        Divider()

        ImagePreviewMenuCommands()

        Divider()

        InspectorButton(viewSettings: viewSettings)
    }
}

// MARK: - Sidebar Mode Section

/// Sidebar mode selection commands (Navigate, Search, Chat, Workflows, Activity)
struct SidebarModeSection: View {
    @ObservedObject var viewSettings: ViewSettings

    var body: some View {
        Section("Sidebar") {
            SidebarModeButton(
                mode: .navigate,
                label: "Navigate",
                icon: "list.bullet.indent",
                shortcut: "1",
                current: viewSettings.sidebarMode
            ) {
                viewSettings.sidebarMode = .navigate
            }

            SidebarModeButton(
                mode: .search,
                label: "Search",
                icon: "magnifyingglass",
                shortcut: "2",
                current: viewSettings.sidebarMode
            ) {
                viewSettings.sidebarMode = .search
            }

            SidebarModeButton(
                mode: .chat,
                label: "Chat",
                icon: "bubble.left.and.bubble.right",
                shortcut: "3",
                current: viewSettings.sidebarMode
            ) {
                viewSettings.sidebarMode = .chat
            }

            SidebarModeButton(
                mode: .workflows,
                label: "Workflows",
                icon: "arrow.triangle.branch",
                shortcut: "4",
                current: viewSettings.sidebarMode
            ) {
                viewSettings.sidebarMode = .workflows
            }

            SidebarModeButton(
                mode: .activity,
                label: "Activity",
                icon: "chart.bar",
                shortcut: "5",
                current: viewSettings.sidebarMode
            ) {
                viewSettings.sidebarMode = .activity
            }

            SidebarModeButton(
                mode: .automation,
                label: "Automation",
                icon: "clock.badge.checkmark",
                shortcut: "6",
                current: viewSettings.sidebarMode
            ) {
                viewSettings.sidebarMode = .automation
            }
        }
    }
}

/// Reusable sidebar mode button with checkmark when active
struct SidebarModeButton: View {
    let mode: SidebarMode
    let label: String
    let icon: String
    let shortcut: String
    let current: SidebarMode
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Label(label, systemImage: icon)
            if current == mode {
                Image(systemName: "checkmark")
            }
        }
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.control, .command]
        )
    }
}

// MARK: - Library Layout Section

/// Library layout selection commands (Icons, List, Table, Map)
struct LibraryLayoutSection: View {
    @ObservedObject var viewSettings: ViewSettings

    var body: some View {
        Section("View") {
            LibraryLayoutButton(
                layout: .icons,
                label: "as Icons",
                icon: "square.grid.2x2",
                shortcut: "1",
                current: viewSettings.libraryLayout
            ) {
                viewSettings.libraryLayout = .icons
            }

            LibraryLayoutButton(
                layout: .list,
                label: "as List",
                icon: "list.bullet",
                shortcut: "2",
                current: viewSettings.libraryLayout
            ) {
                viewSettings.libraryLayout = .list
            }

            LibraryLayoutButton(
                layout: .table,
                label: "as Table",
                icon: "tablecells",
                shortcut: "3",
                current: viewSettings.libraryLayout
            ) {
                viewSettings.libraryLayout = .table
            }

            LibraryLayoutButton(
                layout: .map,
                label: "as Map",
                icon: "rectangle.3.group",
                shortcut: "4",
                current: viewSettings.libraryLayout
            ) {
                viewSettings.libraryLayout = .map
            }
        }
    }
}

/// Reusable library layout button with checkmark when active
struct LibraryLayoutButton: View {
    let layout: LibraryLayout
    let label: String
    let icon: String
    let shortcut: String
    let current: LibraryLayout
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 8) {
                if current == layout {
                    Image(systemName: "checkmark")
                        .frame(width: 12)
                }
                Image(systemName: icon)
                    .frame(width: 16)
                Text(label)
            }
        }
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.command]
        )
    }
}

// MARK: - Preview Mode Section

/// Preview mode selection commands (None, Standard, Widescreen)
struct PreviewModeSection: View {
    @ObservedObject var viewSettings: ViewSettings

    var body: some View {
        Section("Preview") {
            PreviewModeButton(
                mode: .none,
                label: "None",
                icon: "square",
                shortcut: "5",
                current: viewSettings.previewMode
            ) {
                viewSettings.previewMode = .none
            }

            PreviewModeButton(
                mode: .standard,
                label: "Standard",
                icon: "rectangle.split.1x2",
                shortcut: "6",
                current: viewSettings.previewMode
            ) {
                viewSettings.previewMode = .standard
            }

            PreviewModeButton(
                mode: .widescreen,
                label: "Widescreen",
                icon: "rectangle.split.2x1",
                shortcut: "7",
                current: viewSettings.previewMode
            ) {
                viewSettings.previewMode = .widescreen
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
        .keyboardShortcut(
            KeyEquivalent(Character(shortcut)),
            modifiers: [.command]
        )
    }
}

// MARK: - Quick Look Button

/// Quick Look toggle command
struct QuickLookButton: View {
    @ObservedObject var viewSettings: ViewSettings

    var body: some View {
        Button {
            viewSettings.showQuickLook.toggle()
        } label: {
            Label("Quick Look", systemImage: "eye")
        }
        .keyboardShortcut("y", modifiers: [.command])
    }
}

// MARK: - Inspector Button

/// Inspector show/hide command
struct InspectorButton: View {
    @ObservedObject var viewSettings: ViewSettings

    var body: some View {
        Button {
            viewSettings.showInspector.toggle()
        } label: {
            Label(
                viewSettings.showInspector ? "Hide Inspector" : "Show Inspector",
                systemImage: "sidebar.right"
            )
        }
        .keyboardShortcut("i", modifiers: [.command, .option])
    }
}
