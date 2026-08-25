import FicheroAPIClient
import Foundation
import Observation
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "RenditionService")

/// One page's alternative pixels — the archival original, a contrast-enhanced
/// pass, a background-removed copy (2026-08-20 bbox review).
///
/// A rendition never changes WHAT the page is, only how it looks. Anything
/// that changes which content is shown — a split half, a cropped map section —
/// is a different node, not a rendition. That rule is what makes a bounding
/// box portable: a box normalized to the node's frame is valid on every
/// rendition of it, with no arithmetic.
///
/// `transform` is the honest exception. The staging pipeline's `enhanced` pass
/// really is cropped and deskewed relative to the original, so it says so
/// rather than silently moving every box. `nil` is the common case.
struct DocumentRendition: Identifiable, Hashable, Sendable {
    let id: String
    let documentId: String
    /// `original` | `enhanced` | `background_removed` | `rotated` | `crop` |
    /// `thumbnail` | … Free-form: the staging pipeline names new roles
    /// without waiting for a client release.
    let role: String
    let path: String
    let isPrimary: Bool
    let pixelWidth: Int?
    let pixelHeight: Int?
    /// False when the row references bytes that were never written. Kept as a
    /// knowable state rather than a path that fails at render time.
    let isMaterialized: Bool
    /// True when this rendition is NOT in the node's frame (cropped, rotated,
    /// deskewed). A viewer flipping onto it must expect a different shape, and
    /// boxes anchored to the node's frame do not apply unchanged.
    let hasOwnFrame: Bool
    let note: String?

    /// Title-case label for the chrome: `background_removed` → "Background
    /// Removed". Derived rather than tabled so a role the pipeline invents
    /// still renders as words instead of falling through to a raw identifier.
    var displayName: String {
        role
            .split(separator: "_")
            .map { $0.prefix(1).uppercased() + $0.dropFirst() }
            .joined(separator: " ")
    }
}

/// Fetches a document's renditions through the generated OpenAPI client.
///
/// Display ORDER is the engine's, not this type's: the response arrives
/// already sorted (primary first, then role preference, then a deterministic
/// tiebreak) so the preview and any other surface agree what "next" means.
/// Re-sorting here would recreate exactly the disagreement the engine-side
/// decision exists to prevent.
enum RenditionServiceError: Error {
    /// The engine 404ed the bytes — a referenced-but-absent rendition, or a
    /// stale id. Distinct from "no renditions" so the flip can say why.
    case contentUnavailable(renditionId: String)
    case unexpectedResponse
}

@MainActor
@Observable
final class RenditionService {
    private let client: FicheroClient

    private(set) var renditionsByDocument: [String: [DocumentRendition]] = [:]
    private(set) var loadingDocuments: Set<String> = []

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    convenience init(apiClient: APIClient) {
        let ficheroClient = FicheroClient(
            baseURL: EngineConfig.host,
            libraryPath: apiClient.currentLibraryPath ?? "",
            transportMode: EngineConfig.transportMode
        )
        self.init(ficheroClient: ficheroClient)
    }

    /// This document's renditions, in engine order.
    ///
    /// A 404 means the document does not exist and is distinct from a node
    /// that simply has none — folders have none, and so does a node whose
    /// bytes were never materialised. Both surface as an empty list to the
    /// caller, but only the first is logged as a fault, so an empty flip strip
    /// caused by a bad id is diagnosable rather than silent.
    @discardableResult
    func load(documentId: String, forceRefresh: Bool = false) async -> [DocumentRendition] {
        if !forceRefresh, let cached = renditionsByDocument[documentId] {
            return cached
        }
        loadingDocuments.insert(documentId)
        defer { loadingDocuments.remove(documentId) }

        do {
            let response = try await client.api
                .listRenditionsApiDocumentsDocumentIdRenditionsGet(
                    path: .init(documentId: documentId)
                )
            switch response {
            case .ok(let okResponse):
                let list = try okResponse.body.json
                let items = list.items.map(Self.convert)
                renditionsByDocument[documentId] = items
                return items
            case .notFound:
                logger.error(
                    "Renditions requested for a document that does not exist: \(documentId)"
                )
            case .unprocessableContent(let error):
                let detail = try? error.body.json
                logger.error(
                    "Rendition list rejected for \(documentId): \(detail?.detail?.description ?? "validation error")"
                )
            case .undocumented(let status, _):
                logger.error("Rendition list for \(documentId) returned \(status)")
            }
        } catch {
            // Reported, never swallowed: no renditions and a failed fetch look
            // identical on screen, and only one of them is the truth.
            logger.error(
                "Rendition list failed for \(documentId): \(String(describing: error))"
            )
        }
        renditionsByDocument[documentId] = []
        return []
    }

    /// Cached renditions whose bytes are expected to exist, in engine order.
    /// The flip sequence uses this so a referenced-but-absent rendition does
    /// not show the viewer a placeholder every second press.
    func displayable(documentId: String) -> [DocumentRendition] {
        (renditionsByDocument[documentId] ?? []).filter(\.isMaterialized)
    }

    /// One rendition's image bytes — the flip's fetch (up/down axis). Cached
    /// per rendition id: flipping back and forth between two renditions of a
    /// page must not refetch either.
    private var contentCache: [String: Data] = [:]

    func contentData(documentId: String, renditionId: String) async throws -> Data {
        if let cached = contentCache[renditionId] { return cached }
        let response = try await client.api
            .getRenditionContentApiDocumentsDocumentIdRenditionsRenditionIdContentGet(
                .init(path: .init(documentId: documentId, renditionId: renditionId))
            )
        switch response {
        case .ok(let okResponse):
            let body = try okResponse.body.image_Ast_
            // 128MB: archival TIFF-derived renditions run large; the display
            // path's cap is sized for JPEGs and would truncate them.
            let data = try await Data(collecting: body, upTo: 128 * 1024 * 1024)
            contentCache[renditionId] = data
            return data
        case .notFound:
            throw RenditionServiceError.contentUnavailable(renditionId: renditionId)
        default:
            throw RenditionServiceError.unexpectedResponse
        }
    }

    private static func convert(_ item: Components.Schemas.Rendition) -> DocumentRendition {
        DocumentRendition(
            id: item.id ?? UUID().uuidString,
            documentId: item.documentId,
            role: item.role,
            path: item.path,
            isPrimary: item.isPrimary ?? false,
            pixelWidth: item.pixelWidth,
            pixelHeight: item.pixelHeight,
            isMaterialized: item.materialized ?? true,
            // A rendition whose frame is UNPROVEN (marked by the re-anchor
            // pass, bbox step 4) counts as having its own frame: node-frame
            // boxes must SKIP it — blank beats boxes on pixels whose frame
            // nobody can vouch for. Same match-or-skip matrix, one more way
            // to fail closed.
            hasOwnFrame: item.transform != nil || item.frameStatus == "unknown",
            note: item.note
        )
    }
}
