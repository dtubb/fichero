import FicheroAPIClient
import Foundation
import OSLog

extension ActionLibraryService {
    // MARK: - List Operations

    /// Load all actions
    func loadActions() async {
        isLoading = true
        error = nil

        do {
            let response = try await client.api.listActionsApiActionsGet()
            switch response {
            case .ok(let okResponse):
                actions = try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
                logger.info("Loaded \(self.actions.count) actions")
            case .undocumented:
                throw ActionLibraryError.serverError
            }
        } catch {
            self.error = error.localizedDescription
            logger.error("Failed to load actions: \(error.localizedDescription)")
        }

        isLoading = false
    }

    /// Load categories
    func loadCategories() async {
        do {
            let response = try await client.api.listCategoriesApiActionsCategoriesGet()
            switch response {
            case .ok(let okResponse):
                categories = try okResponse.body.json.categories
            case .undocumented:
                return
            }
        } catch {
            logger.error("Failed to load categories: \(error.localizedDescription)")
        }
    }

    /// Load actions by category
    func loadActions(category: String) async -> [ActionItem] {
        do {
            let response = try await client.api.listActionsByCategoryApiActionsCategoryCategoryGet(
                path: .init(category: category),
            )
            switch response {
            case .ok(let okResponse):
                return try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
            case .unprocessableContent, .undocumented:
                return []
            }
        } catch {
            logger.error("Failed to load category: \(error.localizedDescription)")
            return []
        }
    }

    /// Load built-in actions
    func loadBuiltinActions() async -> [ActionItem] {
        do {
            let response = try await client.api.listBuiltinActionsApiActionsBuiltinGet()
            switch response {
            case .ok(let okResponse):
                return try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
            case .undocumented:
                return []
            }
        } catch {
            logger.error("Failed to load builtin actions: \(error.localizedDescription)")
            return []
        }
    }

    /// Load custom actions
    func loadCustomActions() async -> [ActionItem] {
        do {
            let response = try await client.api.listCustomActionsApiActionsCustomGet()
            switch response {
            case .ok(let okResponse):
                return try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
            case .undocumented:
                return []
            }
        } catch {
            logger.error("Failed to load custom actions: \(error.localizedDescription)")
            return []
        }
    }

    /// Load recent actions
    func loadRecentActions(limit: Int = 10) async {
        do {
            let response = try await client.api.listRecentActionsApiActionsRecentGet(
                query: .init(limit: limit),
            )
            switch response {
            case .ok(let okResponse):
                recentActions = try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
            case .unprocessableContent, .undocumented:
                return
            }
        } catch {
            logger.error("Failed to load recent actions: \(error.localizedDescription)")
        }
    }

    /// Load the current library's ACL snapshot for the active user.
    func loadLibraryAuthzSnapshot(targetId: String? = nil) async throws -> Components.Schemas.LibraryAuthzSnapshot {
        let response = try await client.api.getLibraryAuthzSnapshotApiAuthzLibraryGet(
            query: .init(targetId: targetId)
        )
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent, .undocumented:
            throw ActionLibraryError.serverError
        }
    }

    /// List this library's members (roles joined with account profiles) for the
    /// sidebar sharing badge/popover (#2869 A4). Owner-gated on the engine when
    /// multi-user is on; callers surface a thrown error as "no access".
    func listLibraryMembers() async throws -> Components.Schemas.LibraryMembersResponse {
        let response = try await client.api.listLibraryMembersApiAuthzMembersGet(.init())
        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .undocumented:
            throw ActionLibraryError.serverError
        }
    }

    /// Load popular actions. Sets `popularActions` and also returns the list so
    /// the `ActionsService` subclass can vend it directly to its call sites.
    @discardableResult
    func loadPopularActions(limit: Int = 10) async -> [ActionItem] {
        do {
            let response = try await client.api.listPopularActionsApiActionsPopularGet(
                query: .init(limit: limit),
            )
            switch response {
            case .ok(let okResponse):
                let loaded = try decodeModels(from: try okResponse.body.json.items, as: ActionItem.self)
                popularActions = loaded
                return loaded
            case .unprocessableContent, .undocumented:
                return []
            }
        } catch {
            logger.error("Failed to load popular actions: \(error.localizedDescription)")
            return []
        }
    }
}
