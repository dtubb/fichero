import SwiftUI

// MARK: - Display models
// ponytail: plain structs, no Codable/Identifiable overhead — wire to generated client when /api/users is in OpenAPI

struct AppUserDisplay: Identifiable {
    var id: String
    var username: String
    var isOwner: Bool
    var active: Bool
    var libraryRoles: [LibraryRoleDisplay]
}

struct LibraryRoleDisplay: Identifiable {
    var id: String       // library id
    var libraryName: String
    var role: UserLibraryRole
}

enum UserLibraryRole: String, CaseIterable {
    case noAccess = "No Access"
    case viewer   = "Viewer"
    case editor   = "Editor"
    case owner    = "Owner"
}

// MARK: - Users Settings View

struct UsersSettingsView: View {
    // ponytail: stub data — replace with @StateObject UsersStore when /api/users client is generated
    @State private var users: [AppUserDisplay] = AppUserDisplay.stub
    @State private var selectedUserId: String?

    var body: some View {
        if let userId = selectedUserId, let idx = users.firstIndex(where: { $0.id == userId }) {
            UserDetailPane(user: $users[idx], onBack: { selectedUserId = nil })
        } else {
            UsersOverviewPane(users: $users, onSelect: { selectedUserId = $0.id })
        }
    }
}

// MARK: - Overview Pane

private struct UsersOverviewPane: View {
    @Binding var users: [AppUserDisplay]
    let onSelect: (AppUserDisplay) -> Void

    // Unique library names across all users for the access grid
    private var libraryNames: [String] {
        var seen = Set<String>()
        var result: [String] = []
        for user in users {
            for role in user.libraryRoles where !seen.contains(role.libraryName) {
                seen.insert(role.libraryName)
                result.append(role.libraryName)
            }
        }
        return result
    }

    var body: some View {
        Form {
            Section {
                ForEach($users) { $user in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(user.username).fontWeight(.medium)
                            Text(userSummary(user)).font(.caption).foregroundStyle(.secondary)
                        }
                        Spacer()
                        if !user.isOwner {
                            Button("Manage") { onSelect(user) }
                        } else {
                            Button("Change Password") {}
                        }
                    }
                    .padding(.vertical, 2)
                }
            } header: {
                Text("Accounts")
            } footer: {
                Text("Manage who can use Fichero and what they can access.")
                    .foregroundStyle(.secondary)
            }

            if !libraryNames.isEmpty {
                Section("Library Access") {
                    libraryAccessGrid
                }
            }
        }
        .formStyle(.grouped)
    }

    private func userSummary(_ user: AppUserDisplay) -> String {
        if user.isOwner { return "Owner · \(user.libraryRoles.count) \(user.libraryRoles.count == 1 ? "library" : "libraries")" }
        let count = user.libraryRoles.filter { $0.role != .noAccess }.count
        return "\(user.active ? "Active" : "Inactive") · \(count) \(count == 1 ? "library" : "libraries")"
    }

    @ViewBuilder
    private var libraryAccessGrid: some View {
        Grid(alignment: .leading, horizontalSpacing: 0, verticalSpacing: 0) {
            // Header row
            GridRow {
                Text("Library")
                    .font(.caption).fontWeight(.semibold).foregroundStyle(.secondary)
                    .gridCellColumns(1)
                ForEach(users) { user in
                    Text(user.username)
                        .font(.caption).fontWeight(.semibold).foregroundStyle(.secondary)
                        .frame(maxWidth: .infinity)
                }
            }
            .padding(.vertical, 6)
            Divider()

            ForEach(Array(libraryNames.enumerated()), id: \.element) { _, libName in
                GridRow {
                    Text(libName).font(.subheadline)
                    ForEach(users) { user in
                        let role = user.libraryRoles.first(where: { $0.libraryName == libName })?.role
                        Text(role?.rawValue ?? "—")
                            .font(.caption)
                            .foregroundStyle(role == nil || role == .noAccess ? Color.secondary : Color.primary)
                            .frame(maxWidth: .infinity)
                    }
                }
                .padding(.vertical, 6)
                Divider()
            }
        }
        .padding(.horizontal, 4)
    }
}

// MARK: - Per-User Detail Pane

private struct UserDetailPane: View {
    @Binding var user: AppUserDisplay
    let onBack: () -> Void

    var body: some View {
        Form {
            Section {
                HStack {
                    Text("Password")
                    Spacer()
                    Button("Change Password") {}
                }
            } header: {
                Text(user.username)
                    .font(.title2).fontWeight(.bold).textCase(nil)
            } footer: {
                Text("Manage this user's password and library access.")
                    .foregroundStyle(.secondary)
            }

            Section("Library Access") {
                ForEach($user.libraryRoles) { $roleEntry in
                    VStack(alignment: .leading, spacing: 4) {
                        Text(roleEntry.libraryName).fontWeight(.medium)
                        Picker("Role for \(roleEntry.libraryName)", selection: $roleEntry.role) {
                            ForEach(UserLibraryRole.allCases, id: \.self) { roleOption in
                                Text(roleOption.rawValue).tag(roleOption)
                            }
                        }
                        .pickerStyle(.segmented)
                        .labelsHidden()
                        roleHint(for: roleEntry.role)
                    }
                    .padding(.vertical, 2)
                }
            }

            Section {
                Button("Back") { onBack() }
            }
        }
        .formStyle(.grouped)
    }

    @ViewBuilder
    private func roleHint(for role: UserLibraryRole) -> some View {
        let hint: String = switch role {
        case .noAccess: "Cannot access this library."
        case .viewer:   "Can view documents and search."
        case .editor:   "Can add, edit, and run workflows."
        case .owner:    "Full access including user management."
        }
        Text(hint).font(.caption).foregroundStyle(.secondary)
    }
}

// MARK: - Stub data

extension AppUserDisplay {
    // ponytail: replace with live fetch from /api/users + /api/users/{id}/library-roles
    static let stub: [AppUserDisplay] = [
        AppUserDisplay(
            id: "u1", username: "daniel", isOwner: true, active: true,
            libraryRoles: [
                LibraryRoleDisplay(id: "lib1", libraryName: "Colombia Archive", role: .owner),
                LibraryRoleDisplay(id: "lib2", libraryName: "Slipbox", role: .owner),
                LibraryRoleDisplay(id: "lib3", libraryName: "Marshall Diaries", role: .owner)
            ]
        ),
        AppUserDisplay(
            id: "u2", username: "assistant", isOwner: false, active: true,
            libraryRoles: [
                LibraryRoleDisplay(id: "lib1", libraryName: "Colombia Archive", role: .editor),
                LibraryRoleDisplay(id: "lib2", libraryName: "Slipbox", role: .viewer)
            ]
        ),
        AppUserDisplay(
            id: "u3", username: "reader", isOwner: false, active: true,
            libraryRoles: [
                LibraryRoleDisplay(id: "lib1", libraryName: "Colombia Archive", role: .viewer)
            ]
        )
    ]
}

// MARK: - Preview

#Preview("Users Settings") {
    UsersSettingsView()
        .frame(width: 600, height: 500)
}
