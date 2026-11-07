#if canImport(AppKit)
import SwiftUI

extension ShareSettingsView {
    static let nothingSharedSentence = "Sharing is on. No project is shared yet."

    /// With Sharing on and nothing shared, one sentence and the way to the dialog, so Not Now is not the end (#6366).
    @ViewBuilder
    var nothingSharedSection: some View {
        if hostingEnabled, EngineConfig.engineIsLocal,
           ShareWhichProjectsModel.opens(sharedCount: sharingState?.sharedLibraryCount) {
            Section {
                Text(Self.nothingSharedSentence).font(.caption).foregroundStyle(.secondary)
                Button("Share a Project…") { activeSheet = .whichProjects }
                    .accessibilityIdentifier("sharing.whichProjects.shareAProject")
            }
        }
    }

    var whichProjectsSheet: some View {
        ShareWhichProjectsSheet(
            libraries: libraryManager.openLibraries.filter { $0.id != LibraryManager.globalLibraryId },
            multiuser: multiuserEnabled,
            usersStore: appState.usersStore,
            onLink: { first, rest in
                // The sheet has closed; the first project's own Share sheet makes the ONE link for the set (Multi-user off).
                Task { @MainActor in activeSheet = .project(first.id, also: rest.map(\.url.path)) }
            })
        .onDisappear { Task { await refreshSharingState() } }
    }
}
#endif
