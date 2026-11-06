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
        // The addresses the link can carry (`sharing.share-sheet-offers-both-addresses`); a failure leaves the one address.
        await readSharingState()
        if !Self.sharesWithPeople(multiuser: EngineConfig.multiuserEnabled, folder: folder != nil) {
            await mintPairingCodeIfPossible()
        }
    }

    /// Reads the addresses the link can carry, asking a few more times while the forward reads `none` or nothing came back:
    /// the engine makes it just after it is ready. A failed read keeps the last good state (review P1, P2).
    @MainActor
    func readSharingState() async {
        guard EngineConfig.engineIsLocal else { return }
        for attempt in 0..<4 {
            if attempt > 0 {
                try? await Task.sleep(for: .seconds(2))
                if Task.isCancelled { return }
            }
            if let state = try? await PairingService(apiRoot: EngineConfig.host).sharingState() { sharingState = state }
            loadSPKIPin()  // the pin lands after a restart; "still minting" must not stay forever (t73)
            if !PairingCardRefresh.readsForwardAgain(stateLoaded: sharingState != nil, forward: sharingState?.tailnetForward) { return }
        }
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
