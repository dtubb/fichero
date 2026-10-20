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
                    "No project open",
                    systemImage: "person.2",
                    description: Text("Open a project to manage account access.")
                )
            }
        }
    }
}

struct UsersContent: View {
    let store: UsersStore
    let identityStore: IdentityStore
    let library: LibraryManager.LibraryReference

    @State var authzSnapshot: Components.Schemas.LibraryAuthzSnapshot?
    @State var authzError: String?
    @State var pendingUserId: String?
    @State var pendingRole = "editor"
    @State var pendingRoleDrafts: [String: String] = [:]
    @State var isApplyingRoleChange = false

    // The people list: the selected row (what − acts on), the `+` sheet, and a person's Capture… sheet.
    @State var selectedAccountID: String?
    @State var showAddAccount = false
    @State var capturePerson: CapturePersonTarget?
    @State var isCreatingUser = false
    @State var accountError: String?

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

let authzRoles = ["owner", "editor", "viewer"]

struct CapturePersonTarget: Identifiable {
    let id: String
}

// MARK: - Preview

#Preview("Users Settings") {
    UsersSettingsView()
        .environment(AppState())
        .environment(LibraryManager.shared)
        .frame(width: 600, height: 460)
}
