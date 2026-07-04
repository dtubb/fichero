import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

/// One standalone (non-document) canvas item's CONTENT — the *what*, not the
/// *where*. Position lives in a `canvas_layout` row keyed by this same `id`
/// (see `CanvasItemLayout`); this model carries the kind + text + link
/// endpoints. Small display model mirroring the generated
/// `Components.Schemas.CanvasItem`; the store is the only thing that maps it
/// to/from the OpenAPI types.
struct CanvasItemDisplay: Identifiable, Hashable, Codable {
    /// The canvas item id — also the `canvas_layout` key that places it.
    let id: String
    var folderId: String
    var kind: Components.Schemas.CanvasItemKind
    var text: String?
    /// For `kind == .link`: the two item ids the connector joins.
    var sourceItemId: String?
    var targetItemId: String?

    enum CodingKeys: String, CodingKey {
        case id
        case folderId
        case kind
        case text
        case sourceItemId
        case targetItemId
    }

    /// Decode tolerantly: a missing/unknown `kind` falls back to `.note` so one
    /// odd row can't drop the whole list. Mirrors `SpatialNodeType`'s
    /// unknown-default idiom.
    init(from decoder: any Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = try container.decode(String.self, forKey: .id)
        folderId = try container.decode(String.self, forKey: .folderId)
        if let decodedKind = try? container.decode(Components.Schemas.CanvasItemKind.self, forKey: .kind) {
            kind = decodedKind
        } else {
            kind = .note
        }
        text = try container.decodeIfPresent(String.self, forKey: .text)
        sourceItemId = try container.decodeIfPresent(String.self, forKey: .sourceItemId)
        targetItemId = try container.decodeIfPresent(String.self, forKey: .targetItemId)
    }
}

extension CanvasItemDisplay {
    /// Map a generated typed `CanvasItem` (create/update response row) onto the
    /// display model. Returns `nil` for an id-less row (never persisted).
    init?(item: Components.Schemas.CanvasItem) {
        guard let id = item.id else { return nil }
        self.id = id
        self.folderId = item.folderId
        self.kind = item.kind ?? .note
        self.text = item.text
        self.sourceItemId = item.sourceItemId
        self.targetItemId = item.targetItemId
    }
}

/// Observable domain store for a folder's standalone canvas items (#2294).
///
/// The single endpoint accessor for canvas item CONTENT. Sibling to
/// `CanvasLayoutStore` (#2293): that store owns *where* each id sits, this one
/// owns *what* the standalone ids ARE. The 2D canvas observes both — layout for
/// positions, items for the heterogeneous note/quote/text/link content. A view
/// never calls the generated client directly; it observes `items`, `isLoading`,
/// `loadError` and dispatches the named actions below.
///
/// One instance per library, shared across that library's windows.
@MainActor
@Observable
final class CanvasItemStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var items: [CanvasItemDisplay] = []
    private(set) var isLoading = false
    private(set) var loadError: String?

    // ─── Transport: the EXISTING generated client, unchanged ───
    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "CanvasItemStore")

    init(client: FicheroClient) {
        self.client = client
    }

    /// JSON decoder mapping backend snake_case keys onto camelCase properties.
    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    private static let encoder = JSONEncoder()

    // MARK: - Named actions

    /// Load the standalone canvas items for `folderId` into `items`.
    func loadItems(folderId: String) async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let response = try await client.api
                .listCanvasItemsApiCanvasFoldersScopeIdItemsGet(
                    path: .init(scopeId: folderId)
                )
            switch response {
            case .ok(let okResponse):
                let envelope = try okResponse.body.json.items
                items = envelope.compactMap(Self.decode)
                log.info("Loaded \(self.items.count, privacy: .public) canvas items")
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                loadError = detail?.detail?.description ?? "Validation error"
                items = []
            case .undocumented(let code, _):
                loadError = "Unexpected response (\(code))"
                items = []
            }
        } catch {
            loadError = error.localizedDescription
            items = []
            log.error("Canvas items load failed: \(error.localizedDescription)")
        }
    }

    /// Create one standalone canvas item and append it to `items` on success.
    /// For `kind == .link` pass `sourceItemId`/`targetItemId`.
    @discardableResult
    func createItem(
        folderId: String,
        kind: Components.Schemas.CanvasItemKind,
        text: String? = nil,
        sourceItemId: String? = nil,
        targetItemId: String? = nil
    ) async -> CanvasItemDisplay? {
        let body = Components.Schemas.CanvasItemCreateRequest(
            kind: kind,
            text: text,
            sourceItemId: sourceItemId,
            targetItemId: targetItemId
        )
        do {
            let response = try await client.api
                .createCanvasItemApiCanvasFoldersScopeIdItemsPost(
                    path: .init(scopeId: folderId),
                    body: .json(body)
                )
            switch response {
            case .ok(let okResponse):
                guard let created = CanvasItemDisplay(item: try okResponse.body.json) else {
                    loadError = "Created item missing id"
                    return nil
                }
                items.append(created)
                return created
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                loadError = detail?.detail?.description ?? "Validation error"
                return nil
            case .undocumented(let code, _):
                loadError = "Unexpected response (\(code))"
                return nil
            }
        } catch {
            loadError = error.localizedDescription
            log.error("Canvas item create failed: \(error.localizedDescription)")
            return nil
        }
    }

    /// Patch a canvas item's text / kind / link endpoints, replacing the
    /// matching row in `items` with the server's typed response.
    @discardableResult
    func updateItem(
        folderId: String,
        itemId: String,
        kind: Components.Schemas.CanvasItemKind? = nil,
        text: String? = nil,
        sourceItemId: String? = nil,
        targetItemId: String? = nil
    ) async -> Bool {
        let body = Components.Schemas.CanvasItemUpdateRequest(
            kind: kind,
            text: text,
            sourceItemId: sourceItemId,
            targetItemId: targetItemId
        )
        do {
            let response = try await client.api
                .updateCanvasItemApiCanvasFoldersScopeIdItemsItemIdPatch(
                    path: .init(scopeId: folderId, itemId: itemId),
                    body: .json(body)
                )
            switch response {
            case .ok(let okResponse):
                guard let updated = CanvasItemDisplay(item: try okResponse.body.json) else { return false }
                if let index = items.firstIndex(where: { $0.id == updated.id }) {
                    items[index] = updated
                } else {
                    items.append(updated)
                }
                return true
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                loadError = detail?.detail?.description ?? "Validation error"
                return false
            case .undocumented(let code, _):
                loadError = "Unexpected response (\(code))"
                return false
            }
        } catch {
            loadError = error.localizedDescription
            log.error("Canvas item update failed: \(error.localizedDescription)")
            return false
        }
    }

    /// Delete a canvas item and drop it from `items` on success.
    @discardableResult
    func deleteItem(folderId: String, itemId: String) async -> Bool {
        do {
            let response = try await client.api
                .deleteCanvasItemApiCanvasFoldersScopeIdItemsItemIdDelete(
                    path: .init(scopeId: folderId, itemId: itemId)
                )
            switch response {
            case .ok:
                items.removeAll { $0.id == itemId }
                return true
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                loadError = detail?.detail?.description ?? "Validation error"
                return false
            case .undocumented(let code, _):
                loadError = "Unexpected response (\(code))"
                return false
            }
        } catch {
            loadError = error.localizedDescription
            log.error("Canvas item delete failed: \(error.localizedDescription)")
            return false
        }
    }

    /// Decode a single untyped envelope row into a `CanvasItemDisplay`. Returns
    /// `nil` for any malformed row so one bad item can't drop the whole list.
    private static func decode(_ container: OpenAPIValueContainer) -> CanvasItemDisplay? {
        guard let data = try? encoder.encode(container) else { return nil }
        return try? decoder.decode(CanvasItemDisplay.self, from: data)
    }
}
