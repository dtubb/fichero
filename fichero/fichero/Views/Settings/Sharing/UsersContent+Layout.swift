import FicheroAPIClient
import SwiftUI

// MARK: - Layout & View Hierarchy

extension UsersContent {
    @ViewBuilder
    internal var accountList: some View {
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

            // Invite links (#3157) are only meaningful in multi-user mode, and only
            // owners can mint them. When multi-user is off the section used to simply
            // not exist, so a single-user owner never learned invites were a thing,
            // let alone what turned them on. Name it, and name the place.
            //
            // ponytail: it names Engine settings rather than duplicating the
            // multi-user switch here — a second switch over the same state is the
            // exact duplicate-surface disease #3777 just removed.
            if identityStore.isOwnerAccess {
                if authzSnapshot?.multiuserEnabled == true {
                    InviteAccountSection(store: store)
                } else {
                    Section {
                        Text("Multi-user mode is off, so this library has one account and "
                             + "nobody to invite. Turn it on in Settings → Engine, and Fichero "
                             + "will restart its engine to apply it.")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } header: {
                        Text("Invite a Person")
                    }
                }
            }

            sharingSection
        }
        .formStyle(.grouped)
    }

    @ViewBuilder
    internal var addAccountSection: some View {
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
    internal var sharingSection: some View {
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
    internal func roleRow(_ role: Components.Schemas.LibraryRole) -> some View {
        let user = user(for: role.userId)
        let isSelf = role.userId == store.currentUser?.id
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    HStack(spacing: 6) {
                        Text(user.map { displayName(for: $0) } ?? role.userId)
                        if isSelf {
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
                .disabled(isApplyingRoleChange || !isRoleEditable() || isSoleOwner(role))

                // The engine refuses a self-revoke so a library always keeps an
                // owner (authz.remove_role). We SURFACE that rule rather than
                // reimplement it — and rather than silently hiding the button,
                // which teaches the user nothing about why they can't do this.
                if isRoleEditable(), !isSelf {
                    Button("Remove") {
                        Task { await revokeRole(userId: role.userId) }
                    }
                    .buttonStyle(.borderless)
                    .foregroundStyle(.red)
                    .disabled(isApplyingRoleChange)
                }
            }

            if isRoleEditable(), isSelf {
                Text(lastOwnerExplanation(isSoleOwner: isSoleOwner(role)))
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(.vertical, 2)
    }

    @ViewBuilder
    internal func userRow(_ user: Components.Schemas.UserResponse, isCurrent: Bool) -> some View {
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
}
