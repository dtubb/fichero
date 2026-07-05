import FicheroAPIClient
import SwiftUI

/// "Share this library…" surface (#3149, plan §5 F1).
///
/// Pick an existing account — or create a new person inline — assign a role,
/// and share: the engine grants the per-library role through the audited
/// `acl.set` action and returns a `share_url`, shown here to copy / send. The
/// members list manages current roles (change / revoke) via the *same* audited
/// ACL methods the sidebar `LibrarySharingBadge` uses (`setLibraryRole` /
/// `revokeLibraryRole`) — this iterates on that #2869 surface, it does not
/// replace it.
///
/// Presented from the badge popover, so it only appears when multi-user mode is
/// on for this library.
struct ShareLibrarySheet: View {
    let library: LibraryManager.LibraryReference
    let usersStore: UsersStore

    @Environment(\.dismiss) private var dismiss

    // Share form
    @State var personChoice: String = ""
    @State var role = "viewer"
    @State var isSharing = false
    @State var shareURL: String?
    @State var shareError: String?
    @State var copied = false

    // Inline "New person…" create
    @State var newDisplayName = ""
    @State var newUsername = ""
    @State var newPassword = ""
    @State var isCreating = false
    @State var createError: String?

    // Members
    @State var members: [Components.Schemas.LibraryMember] = []
    @State var isLoadingMembers = false
    @State var membersError: String?
    @State var isApplying = false
    @State var manageError: String?

    let shareRoles = ["owner", "editor", "viewer"]
    static let newPersonTag = "__new_person__"

    var body: some View {
        NavigationStack {
            Form {
                shareSection
                membersSection
            }
            .formStyle(.grouped)
            .navigationTitle("Share Library")
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .frame(minWidth: 420, minHeight: 480)
        .task { await loadEverything() }
    }
}

// MARK: - Sections

extension ShareLibrarySheet {
    @ViewBuilder
    var shareSection: some View {
        Section {
            Picker("Person", selection: $personChoice) {
                Text("Choose a person").tag("")
                ForEach(usersStore.users, id: \.id) { user in
                    Text(displayName(user)).tag(user.id)
                }
                Text("New person…").tag(Self.newPersonTag)
            }

            if personChoice == Self.newPersonTag {
                newPersonFields
            }

            Picker("Role", selection: $role) {
                ForEach(shareRoles, id: \.self) { roleName in
                    Text(roleName.capitalized).tag(roleName)
                }
            }

            Button {
                Task { await share() }
            } label: {
                if isSharing {
                    ProgressView().controlSize(.small)
                } else {
                    Text("Share")
                }
            }
            .disabled(isSharing || !canShare)

            if let shareError {
                Text(shareError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        } header: {
            Text("Share With")
        } footer: {
            Text("The person gets the chosen role for this library. Owners manage members; "
                + "editors change content; viewers are read-only.")
                .foregroundStyle(.secondary)
        }

        if let shareURL {
            Section("Share Link") {
                LabeledContent("Link") {
                    Text(shareURL)
                        .textSelection(.enabled)
                        .font(.caption.monospaced())
                        .lineLimit(1)
                        .truncationMode(.middle)
                }
                HStack {
                    Button(copied ? "Copied" : "Copy Link") { copyShareURL() }
                    if let url = URL(string: shareURL) {
                        ShareLink(item: url) {
                            Label("Send…", systemImage: "square.and.arrow.up")
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    var newPersonFields: some View {
        TextField("Full name", text: $newDisplayName)
        TextField("Username", text: $newUsername)
            .textContentType(.username)
        SecureField("Password", text: $newPassword)
            .textContentType(.newPassword)
        Button {
            Task { await createNewPerson() }
        } label: {
            if isCreating {
                ProgressView().controlSize(.small)
            } else {
                Text("Create Person")
            }
        }
        .disabled(isCreating || !canCreatePerson)
        if let createError {
            Text(createError)
                .font(.caption)
                .foregroundStyle(.red)
        }
    }

    @ViewBuilder
    var membersSection: some View {
        Section("Current Members") {
            if isLoadingMembers {
                ProgressView().controlSize(.small)
            } else if let membersError {
                Text(membersError)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else if members.isEmpty {
                Text("No one else has access yet.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                ForEach(members, id: \.userId) { member in
                    memberRow(member)
                }
            }
            if let manageError {
                Text(manageError)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
        }
    }

    @ViewBuilder
    func memberRow(_ member: Components.Schemas.LibraryMember) -> some View {
        HStack(spacing: 8) {
            Image(systemName: member.isOwnerAccount ? "crown" : "person")
                .font(.caption)
                .foregroundStyle(.secondary)
            VStack(alignment: .leading, spacing: 1) {
                Text(member.displayName)
                Text("@\(member.username)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 12)
            Menu(member.role.capitalized) {
                ForEach(shareRoles, id: \.self) { roleName in
                    Button(roleName.capitalized) {
                        Task { await changeRole(userId: member.userId, role: roleName) }
                    }
                }
                Divider()
                Button("Remove", role: .destructive) {
                    Task { await revoke(userId: member.userId) }
                }
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .disabled(isApplying)
        }
    }
}

// MARK: - Actions

extension ShareLibrarySheet {
    var canShare: Bool {
        !personChoice.isEmpty && personChoice != Self.newPersonTag
    }

    var canCreatePerson: Bool {
        !newDisplayName.trimmingCharacters(in: .whitespaces).isEmpty
            && !newUsername.trimmingCharacters(in: .whitespaces).isEmpty
            && !newPassword.isEmpty
    }

    func displayName(_ user: Components.Schemas.UserResponse) -> String {
        user.displayName.isEmpty ? user.username : user.displayName
    }

    @MainActor
    func loadEverything() async {
        await usersStore.load()
        await loadMembers()
    }

    @MainActor
    func loadMembers() async {
        isLoadingMembers = true
        membersError = nil
        defer { isLoadingMembers = false }
        do {
            members = try await library.actionsService.listLibraryMembers().members ?? []
        } catch {
            members = []
            membersError = error.localizedDescription
        }
    }

    /// Create the inline "New person…" account, then select it so the next
    /// Share targets the freshly-created user. The username is matched back to
    /// the reloaded account list to resolve its id.
    @MainActor
    func createNewPerson() async {
        isCreating = true
        createError = nil
        defer { isCreating = false }
        let username = newUsername.trimmingCharacters(in: .whitespaces)
        do {
            try await usersStore.createUser(
                username: username,
                displayName: newDisplayName.trimmingCharacters(in: .whitespaces),
                password: newPassword,
                isOwner: false
            )
            if let created = usersStore.users.first(where: { $0.username == username }) {
                personChoice = created.id
                newDisplayName = ""
                newUsername = ""
                newPassword = ""
            }
        } catch {
            createError = error.localizedDescription
        }
    }

    @MainActor
    func share() async {
        guard canShare else { return }
        isSharing = true
        shareError = nil
        shareURL = nil
        defer { isSharing = false }
        do {
            let response = try await library.actionsService.shareLibrary(user: personChoice, role: role)
            shareURL = response.shareUrl
            await loadMembers()
        } catch {
            shareError = error.localizedDescription
        }
    }

    func copyShareURL() {
        guard let shareURL else { return }
        PlatformPasteboard.writeString(shareURL)
        copied = true
        Task {
            try? await Task.sleep(for: .seconds(2))
            copied = false
        }
    }

    /// Change one member's role in place — update just that row on success so the
    /// list never wholesale re-renders (stable `id: \.userId`).
    @MainActor
    func changeRole(userId: String, role newRole: String) async {
        isApplying = true
        manageError = nil
        defer { isApplying = false }
        do {
            _ = try await library.actionsService.setLibraryRole(userId: userId, role: newRole)
            if let idx = members.firstIndex(where: { $0.userId == userId }) {
                let old = members[idx]
                members[idx] = .init(
                    userId: old.userId,
                    username: old.username,
                    displayName: old.displayName,
                    isOwnerAccount: old.isOwnerAccount,
                    role: newRole
                )
            }
        } catch {
            manageError = error.localizedDescription
        }
    }

    /// Revoke one member — drop just that row on success, no full reload.
    @MainActor
    func revoke(userId: String) async {
        isApplying = true
        manageError = nil
        defer { isApplying = false }
        do {
            _ = try await library.actionsService.revokeLibraryRole(userId: userId)
            members.removeAll { $0.userId == userId }
        } catch {
            manageError = error.localizedDescription
        }
    }
}
