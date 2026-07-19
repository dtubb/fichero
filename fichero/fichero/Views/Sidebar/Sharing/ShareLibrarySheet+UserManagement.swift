import FicheroAPIClient
import SwiftUI

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
}
