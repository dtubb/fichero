import FicheroAPIClient
import Foundation
import OSLog

/// Thin compatibility shim over the canonical `ActionLibraryService` (#1711).
///
/// Both services historically spoke raw `URLSession` to the *same*
/// `/api/actions` surface — duplicate transport. They are now collapsed onto
/// one type: `ActionLibraryService` owns the single generated-client transport
/// and all mapping, and `ActionsService` is a subclass that only re-exposes the
/// handful of method *shapes* its existing call sites
/// (`ActionLibraryView`, `ActionDetailView`) depend on — different argument
/// labels (`actionId:`/`id:`) and a couple that reload `actions` afterwards.
/// Everything else (`loadActions`, `loadCategories`, `loadBuiltinActions`,
/// `loadCustomActions`, `loadPopularActions`, the `@Published` state) is
/// inherited unchanged, so there is no duplicate URLSession glue.
@MainActor
final class ActionsService: ActionLibraryService {
    /// Create an action, then refresh the published `actions` list so list views
    /// pick up the new entry (matches the former `ActionsService` behaviour).
    override func createAction(_ request: CreateActionRequest) async throws -> ActionItem {
        let action = try await super.createAction(request)
        await loadActions()
        return action
    }

    /// Record use — `actionId:`-labelled variant for existing call sites.
    func recordUse(actionId: String) async {
        await recordUse(actionId)
    }

    /// Delete by `id:` then refresh the published `actions` list.
    func deleteAction(id: String) async throws {
        try await deleteAction(id)
        await loadActions()
    }

    /// Get by `id:`, throwing instead of returning `nil`.
    func getAction(id: String) async throws -> ActionItem {
        guard let action = await getAction(id) else {
            throw ActionLibraryError.serverError
        }
        return action
    }

    /// Export by `id:`.
    func exportAction(id: String) async throws -> String {
        try await exportAction(id)
    }

    /// Import from JSON (always with a fresh id), then refresh `actions`.
    func importAction(json: String) async throws -> ActionItem {
        let action = try await importAction(json, newId: true)
        await loadActions()
        return action
    }
}

// MARK: - Models

typealias ActionItem = Components.Schemas.ActionResponse

extension Components.Schemas.ActionResponse: Identifiable {}

// AnyCodable is defined in Models/Document.swift — do not duplicate

struct CreateActionRequest: Encodable {
    let name: String
    var description: String = ""
    var category: String = "custom"
    var tags: [String] = []
    var icon: String = "square.stack.3d.up"
    var nodeTemplate: [String: Any] = [:]
    var nodes: [[String: Any]] = []
    var edges: [[String: Any]] = []
    var author: String = ""

    enum CodingKeys: String, CodingKey {
        case name, description, category, tags, icon
        case nodeTemplate = "node_template"
        case nodes, edges, author
    }

    func encode(to encoder: Encoder) throws {
        var container = encoder.container(keyedBy: CodingKeys.self)
        try container.encode(name, forKey: .name)
        try container.encode(description, forKey: .description)
        try container.encode(category, forKey: .category)
        try container.encode(tags, forKey: .tags)
        try container.encode(icon, forKey: .icon)
        try container.encode(author, forKey: .author)
    }
}
