import Foundation

// MARK: - Presentation State

extension UsersContent {
    internal var presentation: UsersSettingsPresentation {
        UsersSettingsPresentation.resolve(.init(
            isLoading: store.isLoading,
            loadError: store.loadError,
            usersEmpty: store.users.isEmpty,
            hasCurrentUser: store.currentUser != nil,
            hasAuthzSnapshot: authzSnapshot != nil,
            listAccessDenied: store.listAccessDenied,
            isOwnerAccess: identityStore.isOwnerAccess
        ))
    }
}
