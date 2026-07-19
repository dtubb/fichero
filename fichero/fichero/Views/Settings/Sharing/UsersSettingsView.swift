import FicheroAPIClient
import SwiftUI

// MARK: - Users Settings View

/// Settings → Users tab. Shows the signed-in user, all accounts, and the
/// current library’s ACL snapshot/role assignments through the generated
/// OpenAPI client.
struct UsersSettingsView: View {
    @Environment(AppState.self) var appState
    @Environment(LibraryManager.self) var libraryManager

    var body: some View {
        Group {
            if let library = libraryManager.globalLibrary {
                UsersContent(
                    store: appState.usersStore,
                    identityStore: appState.identityStore,
                    library: library
                )
            } else {
                ContentUnavailableView(
                    "No library open",
                    systemImage: "person.2",
                    description: Text("Open a library to manage account access.")
                )
            }
        }
    }
}

private struct UsersContent: View {
    let store: UsersStore
    let identityStore: IdentityStore
    let library: LibraryManager.LibraryReference

    @State private var authzSnapshot: Components.Schemas.LibraryAuthzSnapshot?
    @State private var authzError: String?
    @State private var pendingUserId: String?
    @State private var pendingRole = "editor"
    @State private var pendingRoleDrafts: [String: String] = [:]
    @State private var isApplyingRoleChange = false

    // Add Account form (owner-only)
    @State private var newDisplayName = ""
    @State private var newUsername = ""
    @State private var newPassword = ""
    @State private var newIsOwner = false
    @State private var isCreatingUser = false
    @State private var accountError: String?

    var body: some View {
        Group {
            switch presentation {
            case .loading:
                ProgressView("Loading accounts…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case let .loadError(error):
                ContentUnavailableView(
                    "Couldn’t load accounts",
                    systemImage: "person.2.slash",
                    description: Text(error)
                )
            case .empty:
                ContentUnavailableView(
                    "No accounts",
                    systemImage: "person.2",
                    description: Text("No user accounts were returned by the engine.")
                )
            case .accountDetails:
                accountList
            }
        }
        .task(id: library.id) {
            await loadData()
        }
    }
}

private let authzRoles = ["owner", "editor", "viewer"]

// MARK: - Preview

#Preview("Users Settings") {
    UsersSettingsView()
        .environment(AppState())
        .environment(LibraryManager.shared)
        .frame(width: 600, height: 460)
}
