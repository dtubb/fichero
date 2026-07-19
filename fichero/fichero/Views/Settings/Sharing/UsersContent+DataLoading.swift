import Foundation

// MARK: - Data Loading

extension UsersContent {
    @MainActor
    internal func loadData() async {
        await store.load()
        await refreshAuthz()
        // Pending invites are owner-only; a non-owner probe just returns empty.
        if store.currentUser?.isOwner == true {
            await store.loadInvites()
        }
        syncAddMemberDefaults()
    }

    @MainActor
    internal func refreshAuthz() async {
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
    internal func syncAddMemberDefaults() {
        guard !unassignedUsers.isEmpty else {
            pendingUserId = nil
            return
        }
        if let pendingUserId, unassignedUsers.contains(where: { $0.id == pendingUserId }) {
            return
        }
        pendingUserId = unassignedUsers.first?.id
    }
}
