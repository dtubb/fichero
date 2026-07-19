import FicheroAPIClient
import SwiftUI

extension ShareLibrarySheet {
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
                ForEach(Self.shareRoles, id: \.self) { roleName in
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
