import FicheroAPIClient
import SwiftUI

// MARK: - Layout & View Hierarchy

extension UsersContent {
    @ViewBuilder
    internal var accountList: some View {
        Form {
            if !identityStore.isOwnerAccess {
                Section {
                    Text("Account management is owner-only. Your current access appears below.")
                        .foregroundStyle(.secondary)
                }
            }

            // The people (you first, with the You mark), grey Invited rows, `+` and `−` (`sharing.settings.three-panes`).
            Section {
                ForEach(accountRows) { accountRow($0) }
                if let accountError {
                    Text(accountError).font(.caption).foregroundStyle(.red)
                }
                if identityStore.isOwnerAccess {
                    HStack(spacing: 4) {
                        Button { showAddAccount = true } label: { Image(systemName: "plus") }
                            .help("Add Account")
                            .accessibilityLabel("Add Account")
                            .accessibilityIdentifier("accounts.add")
                        Button { Task { await removeSelectedAccount() } } label: { Image(systemName: "minus") }
                            .help(accountRows.first { $0.id == selectedAccountID }?.removeAction ?? "Select a person")
                            .accessibilityLabel("Disable or revoke the selected account")
                            .accessibilityIdentifier("accounts.remove")
                            .disabled(accountRows.first { $0.id == selectedAccountID }?.removeAction == nil || isCreatingUser)
                        Spacer()
                    }
                    .buttonStyle(.borderless)
                }
            }

            rolesSection
        }
        .formStyle(.grouped)
        .sheet(isPresented: $showAddAccount) {
            AccountsAddSheet(store: store, multiUserOn: authzSnapshot?.multiuserEnabled == true) { showAddAccount = false }
        }
        .sheet(item: $capturePerson) { target in
            CaptureSettingsView(startingUser: target.id, onClose: { capturePerson = nil })
                .frame(minWidth: 460, minHeight: 320)
        }
    }

    /// Until the project's Share sheet takes per-project roles (`sharing.settings.project-share-sheet`), the roles stay here.
    @ViewBuilder
    internal var rolesSection: some View {
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
                    Text("Every account already has a role for this project.")
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
    internal func accountRow(_ row: AccountsPaneModel.Row) -> some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                HStack(spacing: 6) {
                    Text(row.title).fontWeight(.medium)
                    if row.isYou {
                        Text("You")
                            .font(.caption2)
                            .fontWeight(.semibold)
                            .padding(.horizontal, 5)
                            .padding(.vertical, 2)
                            .background(.tint.opacity(0.15), in: Capsule())
                            .foregroundStyle(.tint)
                    }
                }
                Text("@\(row.username)").font(.caption).foregroundStyle(.secondary)
            }
            Spacer()
            if !row.role.isEmpty { Text(row.role).font(.caption).foregroundStyle(.secondary) }
            if row.kind == .person, !row.isActive { Text("Disabled").font(.caption).foregroundStyle(.secondary) }
            if row.kind == .person, identityStore.isOwnerAccess {
                Button("Capture…") { capturePerson = CapturePersonTarget(id: row.username) }
                    .buttonStyle(.borderless)
                    .font(.caption)
            }
        }
        .padding(.vertical, 2)
        .opacity(row.kind == .invited || !row.isActive ? 0.55 : 1)
        .contentShape(Rectangle())
        .background(selectedAccountID == row.id ? Color.secondary.opacity(0.15) : .clear, in: RoundedRectangle(cornerRadius: 6))
        .onTapGesture { selectedAccountID = row.id }
        .accessibilityIdentifier("accounts.row.\(row.id)")
    }
}
