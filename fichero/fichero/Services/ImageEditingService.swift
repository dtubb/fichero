#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import Observation
import FicheroAPIClient
import Foundation
import ImageIO
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageEditingService")

// MARK: - Edit-chain model

/// One non-destructive edit operation in a document's image edit chain.
///
/// The backend stores operations as free-form dicts
/// (`{op, page, params, derived_path, created_at, ...}`) so the chain can
/// grow new op kinds without a schema migration (0.0.x no-migration rule).
/// We keep the original `AnyCodable` payload (`raw`) so a single op can be
/// round-tripped back to the backend `PUT /edits` when the user removes one,
/// while exposing typed accessors for display.
struct ImageEditOperation: Identifiable, Hashable {
    let id = UUID()
    let raw: AnyCodable

    private var dict: [String: Any] { raw.value as? [String: Any] ?? [:] }

    /// Backend op name, e.g. `crop`, `rotate`, `straighten`, `enhance`, `remove_background`, `segment`.
    var opKind: String { (dict["op"] as? String)?.lowercased() ?? "unknown" }

    /// 1-indexed page the op applies to (always 1 for single-image documents).
    var page: Int { dict["page"] as? Int ?? 1 }

    var params: [String: Any] { dict["params"] as? [String: Any] ?? [:] }

    var icon: String {
        switch opKind {
        case "crop": return "crop"
        case "rotate": return "rotate.right"
        case "straighten": return "crop.rotate"
        case "enhance": return "wand.and.stars"
        case "fuzzy_clean": return "sparkles"
        case "remove_background": return "person.crop.rectangle.badge.xmark"
        case "segment": return "square.split.bottomrightquarter"
        case "flip_horizontal", "flip_vertical": return "arrow.left.and.right.righttriangle.left.righttriangle.right"
        case "grayscale": return "circle.lefthalf.filled"
        default: return "slider.horizontal.3"
        }
    }

    var title: String {
        switch opKind {
        case "fuzzy_clean": return "Despeckle"
        default:
            return opKind.split(separator: "_")
                .map { $0.prefix(1).uppercased() + $0.dropFirst() }
                .joined(separator: " ")
        }
    }

    var summary: String {
        switch opKind {
        case "crop":
            let width = params["width"] as? Int ?? 0
            let height = params["height"] as? Int ?? 0
            return "\(width)×\(height) px"
        case "rotate":
            let angle = (params["angle"] as? Double) ?? Double(params["angle"] as? Int ?? 0)
            return String(format: "%.0f°", angle)
        case "straighten":
            let angle = (params["angle"] as? Double) ?? Double(params["angle"] as? Int ?? 0)
            return angle == 0 ? "auto" : String(format: "%.0f°", angle)
        case "enhance":
            var parts: [String] = []
            if let value = params["brightness"] as? Double, value != 1.0 { parts.append(String(format: "bright %.1f", value)) }
            if let value = params["contrast"] as? Double, value != 1.0 { parts.append(String(format: "contrast %.1f", value)) }
            if let value = params["sharpen"] as? Double, value != 1.0 { parts.append(String(format: "sharpen %.1f", value)) }
            if (params["auto_levels"] as? Bool) == true { parts.append("auto-levels") }
            if (params["denoise"] as? Bool) == true { parts.append("denoise") }
            return parts.isEmpty ? "no change" : parts.joined(separator: ", ")
        case "fuzzy_clean":
            var parts: [String] = []
            if let radius = params["despeckle_radius"] as? Int { parts.append("despeckle \(radius)") }
            if (params["background_clean"] as? Bool) == true { parts.append("background clean") }
            return parts.isEmpty ? "despeckle" : parts.joined(separator: ", ")
        case "remove_background":
            return (params["method"] as? String) ?? "opencv"
        case "segment":
            if let count = (dict["segments"] as? [Any])?.count { return "\(count) segment(s)" }
            return (params["method"] as? String) ?? "foreground"
        default:
            return ""
        }
    }

    static func == (lhs: ImageEditOperation, rhs: ImageEditOperation) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

/// A document's ordered, non-destructive image edit chain (#462).
struct ImageEditChain {
    var documentId: String
    var operations: [ImageEditOperation]
    var updatedAt: Date?

    var isEmpty: Bool { operations.isEmpty }
}

// MARK: - Service

/// Image-editing service for the `/api/images` router.
///
/// Chain CRUD (`GET`/`PUT`/`DELETE /edits`) and the six operation POSTs
/// (crop/rotate/straighten/enhance/remove-background/segment) go through the
/// generated `FicheroClient` so the library-path header is injected centrally
/// by `LibraryPathMiddleware` (#3028/#1666) and every call throws on non-`.ok`.
///
/// `loadPreview` runs through the generated `previewImage…Get` op: the backend
/// now declares `/preview` as `image/png`/`image/jpeg` binary (#3028), so the
/// generated client decodes the bytes with the library-path header injected
/// centrally — no raw `URLSession`. `previewURL` remains a plain URL builder
/// (no transport) so host-rebind coverage keeps exercising the resolved path.
@MainActor
@Observable
final class ImageEditingService {
    var isLoading: Bool = false
    var lastError: Error?

    /// Upper bound on a single decoded preview download (mirrors
    /// `StorageService.maxImageBytes`); guards `Data(collecting:)` against a
    /// runaway body.
    private static let maxPreviewBytes = 50 * 1024 * 1024

    private let libraryPath: String
    private let client: FicheroClient

    /// Engine root without `/api`, read live off the wrapped client so a pairing /
    /// Settings host change (#2349) rebinds the raw-bytes `previewURL` path too —
    /// not just the generated `client.api` operations. A stored snapshot here would
    /// strand image previews on the host that was current when the editor opened.
    private var engineURL: URL { client.baseURL }

    /// - Parameter engineURL: Engine root without `/api` (e.g. `http://127.0.0.1:8765`).
    init(libraryPath: String, engineURL: URL = EngineConfig.host, client: FicheroClient? = nil) {
        self.libraryPath = libraryPath
        self.client = client ?? FicheroClient(baseURL: engineURL, libraryPath: libraryPath, transportMode: EngineConfig.transportMode)
    }

    convenience init(apiClient: APIClient) {
        // Strip /api from apiClient.baseURL to get the engine root; the generated
        // client's operation templates already carry the /api prefix.
        // Share the apiClient's wrapped FicheroClient (a reference type) rather
        // than snapshotting a fresh one, so a pairing / Settings host change
        // rebinds this service too (#2349) instead of stranding it on the host
        // that was current when the image editor opened.
        self.init(
            libraryPath: apiClient.currentLibraryPath ?? "",
            engineURL: apiClient.baseURL.deletingLastPathComponent(),
            client: apiClient.client
        )
    }

    // MARK: - Preview

    /// Server-rendered preview URL. `applyEdits=false` returns the original
    /// source bytes; `applyEdits=true` applies the saved chain first.
    func previewURL(documentId: String, applyEdits: Bool, page: Int = 1) -> URL {
        var comps = URLComponents(url: engineURL, resolvingAgainstBaseURL: false)!
        comps.path = "/api/images/\(documentId)/preview"
        comps.queryItems = [
            URLQueryItem(name: "apply_edits", value: applyEdits ? "true" : "false"),
            URLQueryItem(name: "page", value: String(page))
        ]
        return comps.url!
    }

    func loadPreview(documentId: String, applyEdits: Bool, page: Int = 1) async throws -> PreviewImage {
        let response = try await client.api.previewImageApiImagesDocumentIdPreviewGet(.init(
            path: .init(documentId: documentId),
            query: .init(applyEdits: applyEdits, page: page)
        ))
        switch response {
        case .ok(let okResponse):
            // The server renders PNG for images with transparency, otherwise
            // JPEG; both are binary bodies. A `.json` body would mean the spec /
            // handler drifted back to the old JSON modelling.
            let body: OpenAPIRuntime.HTTPBody
            switch okResponse.body {
            case .png(let png):
                body = png
            case .jpeg(let jpeg):
                body = jpeg
            case .json:
                throw ImageEditingError.invalidResponse
            }
            let data = try await Data(collecting: body, upTo: Self.maxPreviewBytes)
            return try await Self.decodePreview(from: data)
        case .unprocessableContent:
            throw ImageEditingError.unexpectedStatus(status: 422, bodyPeek: "validation error")
        case .undocumented(let statusCode, _):
            throw ImageEditingError.unexpectedStatus(status: statusCode, bodyPeek: "<undocumented>")
        }
    }

    nonisolated private static func decodePreview(from data: Data) async throws -> PreviewImage {
        try await Task.detached(priority: .userInitiated) {
            guard let source = CGImageSourceCreateWithData(data as CFData, nil),
                  let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
                throw ImageEditingError.invalidImageData
            }
            let pixelSize = CGSize(width: cgImage.width, height: cgImage.height)
            #if canImport(AppKit)
            return PreviewImage(image: NSImage(cgImage: cgImage, size: pixelSize), pixelSize: pixelSize)
            #elseif canImport(UIKit)
            return PreviewImage(image: UIImage(cgImage: cgImage), pixelSize: pixelSize)
            #endif
        }.value
    }

    // MARK: - Chain read / replace / clear  (GET /api/images/{id}/edits, PUT, DELETE)

    func getChain(documentId: String) async throws -> ImageEditChain {
        let response = try await client.api
            .getEditChainApiImagesDocumentIdEditsGet(path: .init(documentId: documentId))
            .ok.body.json
        return try Self.chain(from: response)
    }

    @discardableResult
    func setOperations(documentId: String, operations: [AnyCodable]) async throws -> ImageEditChain {
        let body = Components.Schemas.ImageEditChainUpsert(operations: try Self.generatedOps(operations))
        let response = try await client.api
            .putEditChainApiImagesDocumentIdEditsPut(path: .init(documentId: documentId), body: .json(body))
            .ok.body.json
        return try Self.chain(from: response)
    }

    @discardableResult
    func removeOperation(documentId: String, at index: Int) async throws -> ImageEditChain {
        let chain = try await getChain(documentId: documentId)
        guard chain.operations.indices.contains(index) else { return chain }
        var survivors = chain.operations
        survivors.remove(at: index)
        return try await setOperations(documentId: documentId, operations: survivors.map(\.raw))
    }

    func resetChain(documentId: String) async throws {
        _ = try await client.api
            .deleteEditChainApiImagesDocumentIdEditsDelete(path: .init(documentId: documentId))
            .noContent
    }

    // MARK: - Operations  (POST /api/images/{id}/operations/*)

    /// Uses the generated `/api/images/{document_id}/operations/crop` operation.
    @discardableResult
    func crop(documentId: String, left: Int, top: Int, width: Int, height: Int, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        let response = try await client.api
            .cropImageApiImagesDocumentIdOperationsCropPost(
                path: .init(documentId: documentId),
                body: .json(.init(left: left, top: top, width: width, height: height, page: page)))
            .ok.body.json
        return try Self.chain(from: response)
    }

    /// Uses the generated `/api/images/{document_id}/operations/rotate` operation.
    @discardableResult
    func rotate(documentId: String, angle: Double, expand: Bool = true, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        let response = try await client.api
            .rotateImageApiImagesDocumentIdOperationsRotatePost(
                path: .init(documentId: documentId),
                body: .json(.init(angle: angle, expand: expand, page: page)))
            .ok.body.json
        return try Self.chain(from: response)
    }

    /// Uses the generated `/api/images/{document_id}/operations/straighten` operation.
    @discardableResult
    func straighten(documentId: String, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        let response = try await client.api
            .straightenImageApiImagesDocumentIdOperationsStraightenPost(
                path: .init(documentId: documentId),
                body: .json(.init(page: page)))
            .ok.body.json
        return try Self.chain(from: response)
    }

    /// Uses the generated `/api/images/{document_id}/operations/enhance` operation.
    @discardableResult
    func enhance(documentId: String, brightness: Double = 1.0, contrast: Double = 1.0,
                 sharpen: Double = 1.0, autoLevels: Bool = false, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        let response = try await client.api
            .enhanceImageApiImagesDocumentIdOperationsEnhancePost(
                path: .init(documentId: documentId),
                body: .json(.init(brightness: brightness, contrast: contrast,
                                  sharpen: sharpen, autoLevels: autoLevels, page: page)))
            .ok.body.json
        return try Self.chain(from: response)
    }

    /// Uses the generated `/api/images/{document_id}/operations/remove-background` operation.
    @discardableResult
    func removeBackground(documentId: String,
                          method: String = "opencv",
                          threshold: Int = 28,
                          page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        let response = try await client.api
            .removeBackgroundImageApiImagesDocumentIdOperationsRemoveBackgroundPost(
                path: .init(documentId: documentId),
                body: .json(.init(method: method, threshold: threshold, page: page)))
            .ok.body.json
        return try Self.chain(from: response)
    }

    /// Uses the generated `/api/images/{document_id}/operations/segment` operation.
    @discardableResult
    func segment(documentId: String, method: String = "foreground", threshold: Int = 28,
                 minArea: Int = 100, maxSegments: Int = 20, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        let response = try await client.api
            .segmentImageApiImagesDocumentIdOperationsSegmentPost(
                path: .init(documentId: documentId),
                body: .json(.init(method: method, threshold: threshold,
                                  minArea: minArea, maxSegments: maxSegments, page: page)))
            .ok.body.json
        return try Self.chain(from: response)
    }

    // MARK: - Decoding helpers

    /// Bridge the generated typed chain response back into the app's free-form
    /// `AnyCodable` currency. Operations stay schema-less (the backend grows new
    /// op kinds without a migration), so we round-trip the generated
    /// `OpenAPIObjectContainer` payloads through JSON rather than hand-map keys.
    static func chain(from response: Components.Schemas.ImageEditChainResponse) throws -> ImageEditChain {
        let opsData = try JSONEncoder().encode(response.operations ?? [])
        let ops = try JSONDecoder().decode([AnyCodable].self, from: opsData)
        return ImageEditChain(
            documentId: response.documentId,
            operations: ops.map { ImageEditOperation(raw: $0) },
            updatedAt: response.updatedAt
        )
    }

    /// Inverse bridge: free-form `AnyCodable` ops → generated upsert payloads.
    static func generatedOps(_ operations: [AnyCodable]) throws
        -> [Components.Schemas.ImageEditChainUpsert.OperationsPayloadPayload] {
        let data = try JSONEncoder().encode(operations)
        return try JSONDecoder().decode(
            [Components.Schemas.ImageEditChainUpsert.OperationsPayloadPayload].self, from: data)
    }
}

// MARK: - Supporting types

struct PreviewImage {
    let image: PlatformImage
    let pixelSize: CGSize
}

enum ImageEditingError: Error, LocalizedError {
    case invalidResponse
    case invalidImageData
    case operationFailed(String)
    case unexpectedStatus(status: Int, bodyPeek: String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse: return "Invalid response from image-editing service"
        case .invalidImageData: return "Could not decode preview image data"
        case .operationFailed(let name): return "Image operation failed: \(name)"
        case let .unexpectedStatus(status, peek): return "Image-editing HTTP \(status): \(peek)"
        }
    }
}
