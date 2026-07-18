import FicheroAPIClient
import SwiftUI

extension DocumentInspectorInfoTab {
    @ViewBuilder
    var sharingSection: some View {
        if currentLibrary != nil {
            infoSection("Sharing") {
                if isLoadingLibraryAuthz {
                    ProgressView("Loading access…")
                } else if let libraryAuthzSnapshot {
                    LabeledContent("Multi-user mode") {
                        Text(libraryAuthzSnapshot.multiuserEnabled ? "Enabled" : "Disabled")
                            .foregroundStyle(libraryAuthzSnapshot.multiuserEnabled ? .primary : .secondary)
                    }
                    LabeledContent("Your role") {
                        Text(libraryAuthzSnapshot.currentUserRole?.capitalized ?? "No role")
                            .foregroundStyle(.secondary)
                    }
                    LabeledContent("This document") {
                        Text(accessSummary(libraryAuthzSnapshot))
                            .foregroundStyle(.secondary)
                    }
                    if libraryAuthzSnapshot.canManageRoles {
                        Text("Owners can manage roles in Settings.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                } else if let libraryAuthzError {
                    Text(libraryAuthzError)
                        .foregroundStyle(.red)
                } else {
                    Text("No access snapshot available.")
                        .foregroundStyle(.secondary)
                }
            }
        }
    }

    var authzLoadKey: String {
        "\(document.id)|\(currentLibrary?.id.uuidString ?? "none")"
    }

    @MainActor
    func loadLibraryAuthzSnapshot() async {
        guard let library = currentLibrary else {
            libraryAuthzSnapshot = nil
            libraryAuthzError = nil
            return
        }

        isLoadingLibraryAuthz = true
        defer { isLoadingLibraryAuthz = false }

        do {
            libraryAuthzSnapshot = try await library.actionsService.loadLibraryAuthzSnapshot(
                targetId: document.id
            )
            libraryAuthzError = nil
        } catch {
            libraryAuthzSnapshot = nil
            libraryAuthzError = error.localizedDescription
        }
    }

    func accessSummary(_ snapshot: Components.Schemas.LibraryAuthzSnapshot) -> String {
        if snapshot.targetCanWrite { return "Read / Write" }
        if snapshot.targetCanRead { return "Read only" }
        return "Blocked"
    }
}
