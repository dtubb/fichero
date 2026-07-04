import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

// x/y/z/w/h/d mirror the geometry schema field names.
// swiftlint:disable identifier_name

/// One item's saved position on a folder's 2D / 3D canvas.
///
/// Small display model mirroring the generated `Components.Schemas.CanvasLayout`
/// schema. The store is the only thing that maps this to/from the generated
/// schemas; Slice 3 (2D wiring) and Slice 4 (RealityKit) read these values and
/// never touch the OpenAPI types directly.
struct CanvasItemLayout: Identifiable, Hashable, Codable {
    /// The library item (document / entity / node) this position belongs to.
    var itemId: String
    var x: Double
    var y: Double
    var z: Double
    var w: Double?
    var h: Double?
    var d: Double?
    var angle: Double
    var zIndex: Int
    var style: String?

    /// Stable identity for SwiftUI: one layout row per item per folder.
    var id: String { itemId }

    init(
        itemId: String,
        x: Double = 0,
        y: Double = 0,
        z: Double = 0,
        w: Double? = nil,
        h: Double? = nil,
        d: Double? = nil,
        angle: Double = 0,
        zIndex: Int = 0,
        style: String? = nil
    ) {
        self.itemId = itemId
        self.x = x
        self.y = y
        self.z = z
        self.w = w
        self.h = h
        self.d = d
        self.angle = angle
        self.zIndex = zIndex
        self.style = style
    }
}
// swiftlint:enable identifier_name

extension CanvasItemLayout {
    /// Map a generated `CanvasLayout` (typed PUT response row) onto the display
    /// model, defaulting the schema's optional-with-default numerics.
    init(schema: Components.Schemas.CanvasLayout) {
        self.init(
            itemId: schema.itemId,
            x: schema.x ?? 0,
            y: schema.y ?? 0,
            z: schema.z ?? 0,
            w: schema.w,
            h: schema.h,
            d: schema.d,
            angle: schema.angle ?? 0,
            zIndex: schema.zIndex ?? 0,
            style: schema.style
        )
    }

    /// Project the display model onto a `CanvasLayoutItem` for the save body.
    var asSaveItem: Components.Schemas.CanvasLayoutItem {
        Components.Schemas.CanvasLayoutItem(
            itemId: itemId,
            x: x,
            y: y,
            z: z,
            w: w,
            h: h,
            d: d,
            angle: angle,
            zIndex: zIndex,
            style: style
        )
    }
}

/// Observable domain store for per-folder canvas layouts (#2293).
///
/// The single endpoint accessor for canvas item-position data. A view never
/// holds raw `@State` position arrays or calls the generated client directly:
/// it observes `layout`, `isLoading`, `isSaving`, and `loadError`, and
/// dispatches the named actions below. Mirrors `SearchStore` (#1903) — the
/// `@MainActor @Observable` domain-store shape — and the live untyped-envelope
/// decode idiom used by the existing OpenAPI service wrappers.
///
/// One instance per library, shared across that library's windows.
@MainActor
@Observable
final class CanvasLayoutStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var layout: [CanvasItemLayout] = []
    private(set) var isLoading = false
    private(set) var isSaving = false
    private(set) var loadError: String?

    // ─── Transport: the EXISTING generated client, unchanged ───
    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "CanvasLayoutStore")

    init(client: FicheroClient) {
        self.client = client
    }

    /// JSON decoder mapping backend snake_case keys onto the camelCase
    /// `CanvasItemLayout` properties.
    private static let decoder: JSONDecoder = {
        let decoder = JSONDecoder()
        decoder.keyDecodingStrategy = .convertFromSnakeCase
        return decoder
    }()

    private static let encoder = JSONEncoder()

    // MARK: - Named actions

    /// Load the saved layout for `folderId` into `layout`.
    func loadLayout(folderId: String) async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        do {
            let response = try await client.api
                .getCanvasLayoutApiCanvasFoldersScopeIdLayoutGet(
                    path: .init(scopeId: folderId)
                )
            switch response {
            case .ok(let okResponse):
                let items = try okResponse.body.json.items
                layout = items.compactMap(Self.decode)
                log.info("Loaded \(self.layout.count, privacy: .public) canvas items")
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                loadError = detail?.detail?.description ?? "Validation error"
                layout = []
            case .undocumented(let code, _):
                loadError = "Unexpected response (\(code))"
                layout = []
            }
        } catch {
            loadError = error.localizedDescription
            layout = []
            log.error("Canvas layout load failed: \(error.localizedDescription)")
        }
    }

    /// Persist `items` as `folderId`'s layout and refresh `layout` from the
    /// server's typed response. Returns `true` on success.
    @discardableResult
    func saveLayout(folderId: String, items: [CanvasItemLayout]) async -> Bool {
        isSaving = true
        loadError = nil
        defer { isSaving = false }
        let body = Components.Schemas.CanvasLayoutSaveRequest(items: items.map(\.asSaveItem))
        do {
            let response = try await client.api
                .saveCanvasLayoutApiCanvasFoldersScopeIdLayoutPut(
                    path: .init(scopeId: folderId),
                    body: .json(body)
                )
            switch response {
            case .ok(let okResponse):
                layout = try okResponse.body.json.items.map(CanvasItemLayout.init(schema:))
                log.info("Saved \(self.layout.count, privacy: .public) canvas items")
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
            log.error("Canvas layout save failed: \(error.localizedDescription)")
            return false
        }
    }

    /// Decode a single untyped envelope item into a `CanvasItemLayout`. Returns
    /// `nil` for any malformed row so one bad item can't drop the whole layout.
    private static func decode(_ container: OpenAPIValueContainer) -> CanvasItemLayout? {
        guard let data = try? encoder.encode(container) else { return nil }
        return try? decoder.decode(CanvasItemLayout.self, from: data)
    }
}
