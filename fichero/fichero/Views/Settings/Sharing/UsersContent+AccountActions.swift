import Foundation

// MARK: - Account Actions

extension UsersContent {
    @MainActor
    internal func setActive(userId: String, active: Bool) async {
        isCreatingUser = true
        accountError = nil
        defer { isCreatingUser = false }
        do {
            try await store.setActive(userId: userId, active: active)
        } catch {
            accountError = error.localizedDescription
        }
    }

    /// What − does to the selected row: revoke an invite, disable or enable a person (never you).
    @MainActor
    internal func removeSelectedAccount() async {
        guard let id = selectedAccountID else { return }
        accountError = nil
        if id.hasPrefix("invite:") {
            do {
                try await store.revokeInvite(id: String(id.dropFirst("invite:".count)))
            } catch { accountError = error.localizedDescription }
            selectedAccountID = nil
        } else if let person = user(for: id), person.id != store.currentUser?.id {
            await setActive(userId: id, active: !person.active)
        }
    }

    internal var accountRows: [AccountsPaneModel.Row] {
        AccountsPaneModel.rows(
            people: allUsers.map {
                .init(id: $0.id, name: $0.displayName, username: $0.username, isOwner: $0.isOwner, isActive: $0.active)
            },
            currentID: store.currentUser?.id,
            invitations: store.invites.map { .init(id: $0.id, name: $0.displayName, username: $0.username) })
    }
}
