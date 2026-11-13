import SwiftUI

/// Where the Items, Source and Reader show/hide controls live (#6563; owner, 2026-11-13). On the Mac they are a group
/// in the window toolbar. On the iPad and iPhone they are the first section of the Workspaces menu: the bar keeps
/// Workspaces, the Inspector toggle and search, which leaves room for the centre island.
enum PaneToggleHome: Equatable {
    case toolbarGroup
    case workspacesMenu

    static func home(isIOS: Bool) -> PaneToggleHome {
        isIOS ? .workspacesMenu : .toolbarGroup
    }

    static var current: PaneToggleHome {
        #if os(iOS)
        home(isIOS: true)
        #else
        home(isIOS: false)
        #endif
    }
}

extension ContentView {
    /// The pane toggles as menu items, for the Workspaces menu on iOS. The same actions and words as the Mac's
    /// toolbar group: the words say Show or Hide, and the Items toggle is disabled when it would hide the last pane.
    @ViewBuilder
    var paneToggleMenuSection: some View {
        if PaneToggleHome.current == .workspacesMenu,
           toolbarVisibility.showPaneToggles,
           Self.showsPaneToggles(
               sidebarMode: sidebarMode,
               compactFlow: Self.shouldUseCompactNavigationFlow(horizontalSizeClass: horizontalSizeClass)
           ) {
            let items = LibraryPaneToggleModel(paneVisibility: paneVisibility)
            Section {
                Button {
                    withAnimation(FrameAnimation.snappy) { setLibraryPaneVisible(!items.isVisible) }
                } label: {
                    Label(items.isVisible ? ItemsPane.hideLabel : ItemsPane.showLabel, systemImage: items.systemImage)
                }
                .disabled(!items.isEnabled)
                Button {
                    setCanvasPaneVisible(!paneVisibility.canvas)
                } label: {
                    Label(paneVisibility.canvas ? SourcePane.hideLabel : SourcePane.showLabel,
                          systemImage: ToolbarSymbols.previewPane)
                }
                Button {
                    setReadingPaneVisible(!paneVisibility.reading)
                } label: {
                    Label(paneVisibility.reading ? "Hide Reader" : "Show Reader", systemImage: ToolbarSymbols.readingPane)
                }
            }
        }
    }
}
