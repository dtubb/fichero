import FicheroAPIClient
import Foundation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "StorageResourceLoader")

/// The single fetch path for a storage resource (thumbnail / display / source)
/// keyed by `documentId`, delegating to the generated OpenAPI client so bytes
/// travel whatever `ClientTransport` the client dials — `.https`, `.uds`, or an
/// in-memory transport — never a hand-built socket or host.
///
/// This is the transport-agnostic core the `fichero-res://` scheme adapters
/// (`URLProtocol`, `WKURLSchemeHandler`, `AVAssetResourceLoaderDelegate`) call.
/// It mirrors the byte-fetch logic already proven by `StorageService`
/// (`thumbnailData` / `displayData` / `getSourceData`) but returns raw bytes +
/// a content type instead of a decoded `Image`, because its consumers are
/// WebKit / AVFoundation / URLSession rather than SwiftUI.
///
/// `@MainActor` because `FicheroClient` is main-actor isolated; the async
/// `fetch` is safe to `await` from an adapter's background context.
@MainActor
final class StorageResourceLoader {
    /// A fetched resource: the bytes plus the MIME content type to report to the
    /// consumer (WebKit/AVFoundation both need an accurate `Content-Type`).
    struct Resource {
        let data: Data
        let contentType: String
    }

    /// Upper bound mirrors `StorageService` so a hostile/huge asset can't grow
    /// memory without limit.
    private static let maxImageBytes = 50 * 1024 * 1024
    private static let maxSourceBytes = 500 * 1024 * 1024

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    /// Fetch a storage resource's bytes + content type through the generated
    /// client. Throws `StorageResourceError` on 404 / unexpected responses so
    /// the adapter can fail the request loudly rather than serve empty bytes.
    ///
    /// - Parameter sourceContentTypeHint: content type to report for `.source`
    ///   fetches (the generated op does not surface the response `Content-Type`;
    ///   the caller derives it from the document's extension). Ignored for
    ///   thumbnail/display, which are always JPEG.
    func fetch(
        kind: StorageResourceKind,
        documentId: String,
        sourceContentTypeHint: String? = nil
    ) async throws -> Resource {
        logger.debug("Fetching \(kind.rawValue, privacy: .public) for \(documentId, privacy: .public)")
        switch kind {
        case .thumbnail:
            return try await fetchThumbnail(documentId: documentId)
        case .display:
            return try await fetchDisplay(documentId: documentId)
        case .source:
            return try await fetchSource(
                documentId: documentId,
                contentTypeHint: sourceContentTypeHint ?? "application/octet-stream"
            )
        }
    }

    private func fetchThumbnail(documentId: String) async throws -> Resource {
        let response = try await client.api.getThumbnailApiStorageThumbnailDocIdGet(
            .init(path: .init(docId: documentId))
        )
        switch response {
        case .ok(let ok):
            let data = try await Data(collecting: try ok.body.jpeg, upTo: Self.maxImageBytes)
            return Resource(data: data, contentType: "image/jpeg")
        case .notFound:
            throw StorageResourceError.notFound(kind: .thumbnail, documentId: documentId)
        default:
            throw StorageResourceError.unexpectedResponse
        }
    }

    private func fetchDisplay(documentId: String) async throws -> Resource {
        let response = try await client.api.getDisplayImageApiStorageDisplayDocIdGet(
            .init(path: .init(docId: documentId))
        )
        switch response {
        case .ok(let ok):
            let data = try await Data(collecting: try ok.body.jpeg, upTo: Self.maxImageBytes)
            return Resource(data: data, contentType: "image/jpeg")
        case .notFound:
            throw StorageResourceError.notFound(kind: .display, documentId: documentId)
        default:
            throw StorageResourceError.unexpectedResponse
        }
    }

    private func fetchSource(documentId: String, contentTypeHint: String) async throws -> Resource {
        logger.debug("Fetching source for \(documentId, privacy: .public)")
        let response = try await client.api.getSourceFileApiStorageSourceDocIdGet(
            .init(path: .init(docId: documentId))
        )
        switch response {
        case .ok(let ok):
            let body = try ok.body.any
            let data = try await Data(collecting: body, upTo: Self.maxSourceBytes)
            return Resource(data: data, contentType: contentTypeHint)
        case .notFound:
            throw StorageResourceError.notFound(kind: .source, documentId: documentId)
        default:
            throw StorageResourceError.unexpectedResponse
        }
    }
}

enum StorageResourceError: Error, LocalizedError {
    case notFound(kind: StorageResourceKind, documentId: String)
    case unexpectedResponse
    /// The `fichero-res://` URL didn't resolve to a registered client — the
    /// library it was minted for is gone. Fail loud, never serve stale bytes.
    case unknownClient(token: String)
    case malformedURL(URL)

    var errorDescription: String? {
        switch self {
        case .notFound(let kind, let documentId):
            return "Storage 404 for \(kind.rawValue)/\(documentId)"
        case .unexpectedResponse:
            return "Unexpected response from storage service"
        case .unknownClient(let token):
            return "No registered storage client for token \(token)"
        case .malformedURL(let url):
            return "Malformed storage resource URL: \(url.absoluteString)"
        }
    }
}
