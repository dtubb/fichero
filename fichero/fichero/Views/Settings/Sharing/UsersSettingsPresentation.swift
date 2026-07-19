import FicheroAPIClient
import Foundation

// MARK: - Users Settings Presentation

enum UsersSettingsPresentation: Equatable {
    struct Input: Equatable {
        let isLoading: Bool
        let loadError: String?
        let usersEmpty: Bool
        let hasCurrentUser: Bool
        let hasAuthzSnapshot: Bool
        let listAccessDenied: Bool
        let isOwnerAccess: Bool
    }

    case loading
    case loadError(String)
    case empty
    case accountDetails

    static func resolve(_ input: Input) -> Self {
        if input.isLoading && input.usersEmpty && !input.hasCurrentUser && !input.hasAuthzSnapshot {
            return .loading
        }
        if let loadError = input.loadError, input.usersEmpty, !input.hasCurrentUser, !input.hasAuthzSnapshot {
            return .loadError(loadError)
        }
        if input.usersEmpty && !input.hasCurrentUser && !input.hasAuthzSnapshot {
            return .empty
        }
        if input.listAccessDenied && !input.isOwnerAccess {
            return .accountDetails
        }
        return .accountDetails
    }
}
