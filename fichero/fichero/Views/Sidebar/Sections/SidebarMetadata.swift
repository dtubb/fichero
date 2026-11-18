import SwiftUI

/// What the sidebar's rows show about an item (`sidebar.filter-menu.shows-toggles`, owner 2026-11-13): exactly two
/// things, each switchable from the bar's Metadata button: a project's sharing state and a run in progress on a row.
/// Nothing else — no item count beside a project (owner 2026-11-16: a top-level count is not helpful).
enum SidebarMetadata: String, CaseIterable, Identifiable {
    case sharingState, runProgress

    var id: String { rawValue }

    /// Where each switch is kept; every one is on until switched off.
    var storageKey: String { "sidebar.metadata.\(rawValue)" }

    var title: String {
        switch self {
        case .sharingState: "Sharing"
        case .runProgress: "Run Progress"
        }
    }
}

/// The sidebar's Metadata menu: the two switches.
struct SidebarMetadataMenu: View {
    @AppStorage(SidebarMetadata.sharingState.storageKey) private var sharingState = true
    @AppStorage(SidebarMetadata.runProgress.storageKey) private var runProgress = true

    var body: some View {
        Toggle(SidebarMetadata.sharingState.title, isOn: $sharingState)
        Toggle(SidebarMetadata.runProgress.title, isOn: $runProgress)
    }
}

#Preview("Sidebar Metadata menu") {
    Menu("Metadata") { SidebarMetadataMenu() }
        .padding()
        .frame(width: 200)
}
