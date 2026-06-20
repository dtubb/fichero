import FicheroAPIClient
import SwiftUI

// MARK: - Users Settings View

/// Settings → Users tab. Shows the signed-in user and all accounts via the
/// generated OpenAPI client (`GET /api/auth/me` + `GET /api/users`).
///
/// Library-access roles are not yet exposed by the backend; that section will
/// be added when the per-library ACL endpoints land.
struct UsersSettingsView: View {
    @EnvironmentObject var appState: AppState

    var body: some View {
        UsersContent(store: appState.usersStore)
    }
}

// MARK: - Content (holds .task so store loads on appear)

private struct UsersContent: View {
    let store: UsersStore

    var body: some View {
        Group {
            if store.isLoading && store.users.isEmpty {
                ProgressView("Loading accounts…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if let error = store.loadError, store.users.isEmpty {
                ContentUnavailableView(
                    "Couldn't load accounts",
                    systemImage: "person.2.slash",
                    description: Text(error)
                )
            } else if store.users.isEmpty && store.currentUser == nil {
                ContentUnavailableView(
                    "No accounts",
                    systemImage: "person.2",
                    description: Text("No user accounts were returned by the engine.")
                )
            } else {
                accountList
            }
        }
        .task { await store.load() }
    }

    @ViewBuilder
    private var accountList: some View {
        Form {
            if let signedInUser = store.currentUser {
                Section {
                    userRow(signedInUser, isCurrent: true)
                } header: {
                    Text("Signed In As")
                }
            }

            if !store.users.isEmpty {
                Section {
                    ForEach(store.users, id: \.id) { user in
                        userRow(user, isCurrent: user.id == store.currentUser?.id)
                    }
                } header: {
                    Text("All Accounts")
                } footer: {
                    Text("Owner accounts can manage users and all libraries.")
                        .foregroundStyle(.secondary)
                }
            }
        }
        .formStyle(.grouped)
    }

    @ViewBuilder
    private func userRow(_ user: Components.Schemas.UserResponse, isCurrent: Bool) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(user.displayName.isEmpty ? user.username : user.displayName)
                        .fontWeight(.medium)
                    if isCurrent {
                        Text("You")
                            .font(.caption2).fontWeight(.semibold)
                            .padding(.horizontal, 5).padding(.vertical, 2)
                            .background(.tint.opacity(0.15), in: Capsule())
                            .foregroundStyle(.tint)
                    }
                }
                Text("@\(user.username)")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            HStack(spacing: 6) {
                if user.isOwner {
                    Label("Owner", systemImage: "crown")
                        .font(.caption).foregroundStyle(.secondary)
                        .labelStyle(.iconOnly)
                }
                if !user.active {
                    Text("Inactive")
                        .font(.caption2)
                        .padding(.horizontal, 5).padding(.vertical, 2)
                        .background(.secondary.opacity(0.15), in: Capsule())
                        .foregroundStyle(.secondary)
                }
            }
        }
        .padding(.vertical, 2)
    }
}

// MARK: - Preview

#Preview("Users Settings") {
    UsersSettingsView()
        .environmentObject(AppState())
        .frame(width: 600, height: 400)
}
