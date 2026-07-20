#if canImport(AppKit)
import FicheroAPIClient
import SwiftUI

extension ShareSettingsView {
    // MARK: - Authz

    @MainActor
    func loadAuthzSnapshot() async {
        guard let library = libraryManager.globalLibrary else {
            authzSnapshot = nil
            authzError = nil
            return
        }

        isLoadingAuthz = true
        authzError = nil
        defer { isLoadingAuthz = false }

        do {
            authzSnapshot = try await library.actionsService.loadLibraryAuthzSnapshot()
        } catch {
            authzSnapshot = nil
            authzError = error.localizedDescription
        }
    }

    func authzAccessSummary(_ snapshot: Components.Schemas.LibraryAuthzSnapshot) -> String {
        if snapshot.canManageRoles { return "Owner" }
        if snapshot.targetCanWrite { return "Read / Write" }
        if snapshot.targetCanRead { return "Read only" }
        return "Blocked"
    }
}
#endif
