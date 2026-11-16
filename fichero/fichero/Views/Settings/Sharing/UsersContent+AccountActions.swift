import Foundation

// MARK: - Account Actions

extension UsersContent {
    @MainActor
    internal func setActive(userId: String, active: Bool) async {
        isCreatingUser = true
        defer { isCreatingUser = false }
        do {
            try await store.setActive(userId: userId, active: active)
        } catch {
            showFailure(error, active ? "Couldn't enable that person" : "Couldn't disable that person")
        }
    }

    /// A failed account or role change as the one alert (`sharing.alerts.no-bottom-strip`): the engine's words, and on a 403
    /// Sign In as Owner (`OwnerSignInCoordinator.run`).
    @MainActor
    internal func showFailure(_ error: Error, _ title: String) {
        let ownerSignIn = appState.ownerSignIn
        failurePrompt = SharingFailurePrompt.make(
            sharing: error, title: title, offers: [.signInAsOwner],
            perform: { _ in Task { await ownerSignIn.run() } }, copy: { PlatformPasteboard.writeString($0) })
    }

    /// What − does to the selected row: revoke an invite, disable or enable a person (never you).
    @MainActor
    internal func removeSelectedAccount() async {
        guard let id = selectedAccountID else { return }
        if id.hasPrefix("invite:") {
            do {
                try await store.revokeInvite(id: String(id.dropFirst("invite:".count)))
            } catch { showFailure(error, "Couldn't withdraw the invitation") }
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
