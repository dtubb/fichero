import SwiftUI

/// The panes the Workspaces menu and View ▸ Panes list, each with a check while it is visible (#6730). Which panes show is
/// part of the workspace, so toggling one changes the current workspace; the toolbar has no Hide Items, Hide Source or
/// Hide Reader buttons.
enum PaneMenuEntry: CaseIterable, Equatable {
    case items, source, reader, inspector

    var title: String {
        switch self {
        case .items: ItemsPane.name
        case .source: SourcePane.name
        case .reader: "Reader"
        case .inspector: "Inspector"
        }
    }

    var systemImage: String {
        switch self {
        case .items: ToolbarSymbols.libraryPane
        case .source: ToolbarSymbols.previewPane
        case .reader: ToolbarSymbols.readingPane
        case .inspector: "sidebar.right"
        }
    }

    /// Whether this pane is checked: the content panes read the pane list's visibility, the Inspector its own flag.
    func isChecked(_ visibility: PaneVisibility, inspector: Bool) -> Bool {
        switch self {
        case .items: visibility.grid
        case .source: visibility.canvas
        case .reader: visibility.reading
        case .inspector: inspector
        }
    }
}

extension ContentView {
    /// The panes as checked menu items, the Workspaces menu's first section. The Items toggle is disabled when it would hide
    /// the last pane.
    @ViewBuilder
    var paneToggleMenuSection: some View {
        if Self.showsPaneToggles(
            sidebarMode: sidebarMode,
            compactFlow: Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass)
        ) {
            let items = LibraryPaneToggleModel(paneVisibility: paneVisibility)
            Section {
                ForEach(PaneMenuEntry.allCases, id: \.self) { entry in
                    Toggle(isOn: Binding(
                        get: { entry.isChecked(paneVisibility, inspector: showInspectorSidebar) },
                        set: { setPaneMenuEntry(entry, visible: $0) }
                    )) {
                        Label(entry.title, systemImage: entry.systemImage)
                    }
                    .disabled(entry == .items && !items.isEnabled)
                }
            }
        }
    }

    private func setPaneMenuEntry(_ entry: PaneMenuEntry, visible: Bool) {
        switch entry {
        case .items: withAnimation(FrameAnimation.snappy) { setLibraryPaneVisible(visible) }
        case .source: setCanvasPaneVisible(visible)
        case .reader: setReadingPaneVisible(visible)
        case .inspector: showInspectorSidebar = visible
        }
    }
}
