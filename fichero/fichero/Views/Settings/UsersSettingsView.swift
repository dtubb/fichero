import FicheroAPIClient
import SwiftUI

// swiftlint:disable file_length

// MARK: - Users Settings View

/// Settings → Users tab. Shows the signed-in user, all accounts, and the
/// current library's ACL snapshot/role assignments through the generated
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

// MARK: - Content

enum UsersSettingsPresentation: Equatable {
    struct Input: Equatable {
        let isLoading: Bool
        let loadError: String?
        let usersEmpty: Bool
        let hasCurrentUser: Bool
        let hasAuthzSnapshot: Bool
        let listAccessDenied: Bool
        let isOwnerAccess: Bool
    }

    case loading
    case loadError(String)
    case empty
    case accountDetails

    static func resolve(_ input: Input) -> Self {
        if input.isLoading && input.usersEmpty && !input.hasCurrentUser && !input.hasAuthzSnapshot {
            return .loading
        }
        if let loadError = input.loadError, input.usersEmpty, !input.hasCurrentUser, !input.hasAuthzSnapshot {
            return .loadError(loadError)
        }
        if input.usersEmpty && !input.hasCurrentUser && !input.hasAuthzSnapshot {
            return .empty
        }
        if input.listAccessDenied && !input.isOwnerAccess {
            return .accountDetails
        }
        return .accountDetails
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

extension UsersContent {
    fileprivate var presentation: UsersSettingsPresentation {
        UsersSettingsPresentation.resolve(.init(
            isLoading: store.isLoading,
            loadError: store.loadError,
            usersEmpty: store.users.isEmpty,
            hasCurrentUser: store.currentUser != nil,
            hasAuthzSnapshot: authzSnapshot != nil,
            listAccessDenied: store.listAccessDenied,
            isOwnerAccess: identityStore.isOwnerAccess
        ))
    }

    @ViewBuilder
    fileprivate var accountList: some View {
        Form {
            if let signedInUser = store.currentUser {
                Section {
                    userRow(signedInUser, isCurrent: true)
                } header: {
                    Text("Signed In As")
                }
            }

            if identityStore.isOwnerAccess && !store.users.isEmpty {
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

            if !identityStore.isOwnerAccess {
                Section {
                    Text("Account management is owner-only. Your current access appears below.")
                        .foregroundStyle(.secondary)
                } header: {
                    Text("Accounts")
                }
            }

            if identityStore.isOwnerAccess {
                addAccountSection
            }

            // Invite links (#3157) are only meaningful in multi-user mode, and
            // only owners can mint them.
            if identityStore.isOwnerAccess, authzSnapshot?.multiuserEnabled == true {
                InviteAccountSection(store: store)
            }

            sharingSection
        }
        .formStyle(.grouped)
    }

    @ViewBuilder
    fileprivate var addAccountSection: some View {
        Section {
            TextField("Full name", text: $newDisplayName)
            TextField("Username", text: $newUsername)
                .textContentType(.username)
            SecureField("Password", text: $newPassword)
                .textContentType(.newPassword)
            Toggle("Owner (can manage users and all libraries)", isOn: $newIsOwner)

            if let accountError {
                Text(accountError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }

            Button {
                Task { await createAccount() }
            } label: {
                if isCreatingUser {
                    ProgressView().controlSize(.small)
                } else {
                    Text("Create Account")
                }
            }
            .disabled(isCreatingUser || !canCreateAccount)
        } header: {
            Text("Add Account")
        } footer: {
            Text("New accounts sign in with their username and password.")
                .foregroundStyle(.secondary)
        }
    }

    @ViewBuilder
    fileprivate var sharingSection: some View {
        Section {
            if let authzSnapshot {
                LabeledContent("Multi-user mode") {
                    authzStatusText(authzSnapshot.multiuserEnabled)
                }
                LabeledContent("Role management") {
                    authzStatusText(authzSnapshot.canManageRoles)
                }
                LabeledContent("Your role") {
                    Text(authzSnapshot.currentUserRole?.capitalized ?? "No role")
                        .foregroundStyle(.secondary)
                }
                LabeledContent("Library access") {
                    Text(targetAccessText(authzSnapshot))
                        .foregroundStyle(.secondary)
                }
            } else if let authzError {
                Text(authzError)
                    .foregroundStyle(.red)
            } else {
                ProgressView("Loading sharing…")
            }
        } header: {
            Text("Library Sharing")
        } footer: {
            Text("Owners can assign roles for the current library when multi-user mode is enabled.")
                .foregroundStyle(.secondary)
        }

        if let authzSnapshot, authzSnapshot.canManageRoles {
            Section("Assigned Roles") {
                if sortedRoles.isEmpty {
                    Text("No roles assigned yet.")
                        .foregroundStyle(.secondary)
                } else {
                    ForEach(sortedRoles, id: \.id) { role in
                        roleRow(role)
                    }
                }
            }

            Section("Add Member") {
                if unassignedUsers.isEmpty {
                    Text("Every account already has a role for this library.")
                        .foregroundStyle(.secondary)
                } else {
                    Picker("User", selection: $pendingUserId) {
                        Text("Choose a user").tag(String?.none)
                        ForEach(unassignedUsers, id: \.id) { user in
                            Text(displayName(for: user)).tag(String?.some(user.id))
                        }
                    }

                    Picker("Role", selection: $pendingRole) {
                        ForEach(authzRoles, id: \.self) { role in
                            Text(role.capitalized).tag(role)
                        }
                    }

                    Button {
                        Task { await assignPendingRole() }
                    } label: {
                        if isApplyingRoleChange {
                            ProgressView().controlSize(.small)
                        } else {
                            Text("Add Role")
                        }
                    }
                    .disabled(isApplyingRoleChange || pendingUserId == nil)
                }
            }
        }
    }

    @ViewBuilder
    fileprivate func roleRow(_ role: Components.Schemas.LibraryRole) -> some View {
        let user = user(for: role.userId)
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(user.map { displayName(for: $0) } ?? role.userId)
                    if user?.id == store.currentUser?.id {
                        Text("You")
                            .font(.caption2)
                            .fontWeight(.semibold)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(.tint.opacity(0.15), in: Capsule())
                            .foregroundStyle(.tint)
                    }
                }
                Text(user.map { "@\($0.username)" } ?? role.userId)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Spacer()

            Picker("Role", selection: roleBinding(for: role)) {
                ForEach(authzRoles, id: \.self) { roleName in
                    Text(roleName.capitalized).tag(roleName)
                }
            }
            .labelsHidden()
            .pickerStyle(.menu)
            .frame(width: 120)
            .disabled(isApplyingRoleChange || !isRoleEditable())

            // Revoke, hidden for your own row — the engine also refuses a
            // self-revoke so the sole owner can't lock themselves out.
            if isRoleEditable(), role.userId != store.currentUser?.id {
                Button("Remove") {
                    Task { await revokeRole(userId: role.userId) }
                }
                .buttonStyle(.borderless)
                .foregroundStyle(.red)
                .disabled(isApplyingRoleChange)
            }
        }
        .padding(.vertical, 2)
    }

    fileprivate func roleBinding(for role: Components.Schemas.LibraryRole) -> Binding<String> {
        Binding(
            get: { pendingRoleDrafts[role.userId] ?? role.role },
            set: { newRole in
                pendingRoleDrafts[role.userId] = newRole
                Task { await updateRole(userId: role.userId, role: newRole) }
            }
        )
    }

    @ViewBuilder
    fileprivate func userRow(_ user: Components.Schemas.UserResponse, isCurrent: Bool) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(displayName(for: user))
                        .fontWeight(.medium)
                    if isCurrent {
                        Text("You")
                            .font(.caption2)
                            .fontWeight(.semibold)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(.tint.opacity(0.15), in: Capsule())
                            .foregroundStyle(.tint)
                    }
                }
                Text("@\(user.username)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            HStack(spacing: 6) {
                if user.isOwner {
                    Label("Owner", systemImage: "crown")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .labelStyle(.iconOnly)
                }
                if !user.active {
                    Text("Inactive")
                        .font(.caption2)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(.secondary.opacity(0.15), in: Capsule())
                        .foregroundStyle(.secondary)
                }
                // Owners can disable/enable other accounts (never themselves).
                if store.currentUser?.isOwner == true, !isCurrent {
                    Button(user.active ? "Disable" : "Enable") {
                        Task { await setActive(userId: user.id, active: !user.active) }
                    }
                    .buttonStyle(.borderless)
                    .font(.caption)
                    .disabled(isCreatingUser)
                }
            }
        }
        .padding(.vertical, 2)
    }

    fileprivate var canCreateAccount: Bool {
        !newDisplayName.trimmingCharacters(in: .whitespaces).isEmpty
            && !newUsername.trimmingCharacters(in: .whitespaces).isEmpty
            && !newPassword.isEmpty
    }

    @MainActor
    fileprivate func createAccount() async {
        isCreatingUser = true
        accountError = nil
        defer { isCreatingUser = false }
        do {
            try await store.createUser(
                username: newUsername.trimmingCharacters(in: .whitespaces),
                displayName: newDisplayName.trimmingCharacters(in: .whitespaces),
                password: newPassword,
                isOwner: newIsOwner
            )
            newDisplayName = ""
            newUsername = ""
            newPassword = ""
            newIsOwner = false
            syncAddMemberDefaults()
        } catch {
            accountError = error.localizedDescription
        }
    }

    @MainActor
    fileprivate func setActive(userId: String, active: Bool) async {
        isCreatingUser = true
        accountError = nil
        defer { isCreatingUser = false }
        do {
            try await store.setActive(userId: userId, active: active)
        } catch {
            accountError = error.localizedDescription
        }
    }

    @MainActor
    fileprivate func loadData() async {
        await store.load()
        await refreshAuthz()
        // Pending invites are owner-only; a non-owner probe just returns empty.
        if store.currentUser?.isOwner == true {
            await store.loadInvites()
        }
        syncAddMemberDefaults()
    }

    @MainActor
    fileprivate func refreshAuthz() async {
        authzError = nil
        do {
            authzSnapshot = try await library.actionsService.loadLibraryAuthzSnapshot()
            pendingRoleDrafts.removeAll()
        } catch {
            authzSnapshot = nil
            authzError = error.localizedDescription
        }
    }

    @MainActor
    fileprivate func syncAddMemberDefaults() {
        guard !unassignedUsers.isEmpty else {
            pendingUserId = nil
            return
        }
        if let pendingUserId, unassignedUsers.contains(where: { $0.id == pendingUserId }) {
            return
        }
        pendingUserId = unassignedUsers.first?.id
    }

    @MainActor
    fileprivate func assignPendingRole() async {
        guard let pendingUserId else { return }
        await updateRole(userId: pendingUserId, role: pendingRole)
    }

    @MainActor
    fileprivate func updateRole(userId: String, role: String) async {
        guard authzSnapshot?.canManageRoles == true else { return }
        isApplyingRoleChange = true
        authzError = nil
        defer { isApplyingRoleChange = false }

        do {
            try await library.actionsService.setLibraryRole(userId: userId, role: role)
            await refreshAuthz()
            syncAddMemberDefaults()
        } catch {
            authzError = error.localizedDescription
            pendingRoleDrafts.removeValue(forKey: userId)
        }
    }

    @MainActor
    fileprivate func revokeRole(userId: String) async {
        guard authzSnapshot?.canManageRoles == true else { return }
        isApplyingRoleChange = true
        authzError = nil
        defer { isApplyingRoleChange = false }

        do {
            try await library.actionsService.revokeLibraryRole(userId: userId)
            await refreshAuthz()
            syncAddMemberDefaults()
        } catch {
            authzError = error.localizedDescription
        }
    }

    fileprivate func user(for userId: String) -> Components.Schemas.UserResponse? {
        allUsers.first(where: { $0.id == userId })
    }

    fileprivate var allUsers: [Components.Schemas.UserResponse] {
        var seen = Set<String>()
        return ([store.currentUser] + store.users).compactMap { $0 }.filter { user in
            seen.insert(user.id).inserted
        }
    }

    fileprivate var sortedRoles: [Components.Schemas.LibraryRole] {
        (authzSnapshot?.roles ?? []).sorted { lhs, rhs in
            let lhsRank = roleRank(lhs.role)
            let rhsRank = roleRank(rhs.role)
            if lhsRank != rhsRank { return lhsRank < rhsRank }
            return displayName(for: user(for: lhs.userId) ?? placeholderUser(lhs.userId))
                < displayName(for: user(for: rhs.userId) ?? placeholderUser(rhs.userId))
        }
    }

    fileprivate var unassignedUsers: [Components.Schemas.UserResponse] {
        let assignedIds = Set((authzSnapshot?.roles ?? []).map { $0.userId })
        return allUsers.filter { !assignedIds.contains($0.id) }
    }

    fileprivate func roleRank(_ role: String) -> Int {
        switch role.lowercased() {
        case "owner":
            return 0
        case "editor":
            return 1
        default:
            return 2
        }
    }

    fileprivate func isRoleEditable() -> Bool {
        authzSnapshot?.canManageRoles == true
    }

    fileprivate func targetAccessText(_ snapshot: Components.Schemas.LibraryAuthzSnapshot) -> String {
        if snapshot.targetCanWrite { return "Read / Write" }
        if snapshot.targetCanRead { return "Read only" }
        return "Blocked"
    }

    fileprivate func authzStatusText(_ isOn: Bool) -> some View {
        Text(isOn ? "Enabled" : "Disabled")
            .foregroundStyle(isOn ? Color.accentColor : .secondary)
    }

    fileprivate func displayName(for user: Components.Schemas.UserResponse) -> String {
        user.displayName.isEmpty ? user.username : user.displayName
    }

    fileprivate func placeholderUser(_ userId: String) -> Components.Schemas.UserResponse {
        .init(
            id: userId,
            username: userId,
            displayName: userId,
            isOwner: false,
            active: true,
            createdAt: .now
        )
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
