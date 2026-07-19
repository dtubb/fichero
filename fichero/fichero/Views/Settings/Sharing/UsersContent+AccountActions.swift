import Foundation

// MARK: - Account Actions

extension UsersContent {
    internal var canCreateAccount: Bool {
        !newDisplayName.trimmingCharacters(in: .whitespaces).isEmpty
            && !newUsername.trimmingCharacters(in: .whitespaces).isEmpty
            && !newPassword.isEmpty
    }

    @MainActor
    internal func createAccount() async {
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
}
