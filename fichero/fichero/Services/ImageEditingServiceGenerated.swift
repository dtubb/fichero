import AppKit
import FicheroAPIClient
import Foundation
import ImageIO
import OpenAPIRuntime
import OpenAPIURLSession
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageEditingServiceGenerated")

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

    /// Backend op name, e.g. `crop`, `rotate`, `enhance`, `remove_background`, `segment`.
    var opKind: String { (dict["op"] as? String)?.lowercased() ?? "unknown" }

    /// 1-indexed page the op applies to (always 1 for single-image documents).
    var page: Int { dict["page"] as? Int ?? 1 }

    var params: [String: Any] { dict["params"] as? [String: Any] ?? [:] }

    var icon: String {
        switch opKind {
        case "crop": return "crop"
        case "rotate": return "rotate.right"
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
        case "fuzzy_clean": return "Fuzzy Clean"
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

/// Image-editing service backed by the generated OpenAPI client (`/api/images`).
///
/// Wiring strategy:
///   * The five operation POSTs (crop/rotate/enhance/remove-background/segment)
///     go through the **typed** client so request bodies use the declared
///     `Components.Schemas.*OperationRequest` fields — never `additionalProperties`
///     (constitution Rule #4).
///   * Chain read (`GET /edits`), replace (`PUT /edits`), clear (`DELETE /edits`)
///     and the binary `GET /preview` use raw `URLSession` + `addEngineAuth`,
///     because the `operations` payload is free-form JSON and the preview is
///     raw image bytes — mirroring `StorageServiceGenerated`'s image path.
@MainActor
final class ImageEditingServiceGenerated: ObservableObject {
    @Published var isLoading: Bool = false
    @Published var lastError: Error?

    private let client: FicheroClient
    private let session = URLSession.shared
    private let baseURL: URL

    init(ficheroClient: FicheroClient, baseURL: URL = URL(string: "http://127.0.0.1:8765/api")!) {
        self.client = ficheroClient
        self.baseURL = baseURL
    }

    convenience init(apiClient: APIClient) {
        let libraryPath = apiClient.currentLibraryPath ?? ""
        let ficheroClient = FicheroClient(libraryPath: libraryPath)
        self.init(ficheroClient: ficheroClient, baseURL: apiClient.baseURL)
    }

    private var libraryPath: String { client.currentLibraryPath ?? "" }

    // MARK: - Preview

    /// Server-rendered preview URL. `applyEdits=false` returns the original
    /// source bytes; `applyEdits=true` applies the saved chain first — this is
    /// the entire mechanism behind the #469 original↔edited toggle.
    func previewURL(documentId: String, applyEdits: Bool, page: Int = 1) -> URL {
        var components = URLComponents(
            url: baseURL.appendingPathComponent("images/\(documentId)/preview"),
            resolvingAgainstBaseURL: false
        )
        components?.queryItems = [
            URLQueryItem(name: "apply_edits", value: applyEdits ? "true" : "false"),
            URLQueryItem(name: "page", value: String(page))
        ]
        return components?.url ?? baseURL.appendingPathComponent("images/\(documentId)/preview")
    }

    /// Fetch and decode a preview as an `NSImage`, also reporting the pixel
    /// dimensions (needed to map marquee selections back to source pixels).
    func loadPreview(documentId: String, applyEdits: Bool, page: Int = 1) async throws -> PreviewImage {
        let url = previewURL(documentId: documentId, applyEdits: applyEdits, page: page)
        var request = URLRequest(url: url)
        request.addEngineAuth(libraryPath: libraryPath)
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else {
            throw ImageEditingError.invalidResponse
        }
        guard http.statusCode == 200 else {
            let peek = String(data: data.prefix(200), encoding: .utf8) ?? "<binary>"
            throw ImageEditingError.unexpectedStatus(status: http.statusCode, bodyPeek: peek)
        }
        return try await Self.decodePreview(from: data)
    }

    nonisolated private static func decodePreview(from data: Data) async throws -> PreviewImage {
        try await Task.detached(priority: .userInitiated) {
            guard let source = CGImageSourceCreateWithData(data as CFData, nil),
                  let cgImage = CGImageSourceCreateImageAtIndex(source, 0, nil) else {
                throw ImageEditingError.invalidImageData
            }
            let pixelSize = CGSize(width: cgImage.width, height: cgImage.height)
            let nsImage = NSImage(cgImage: cgImage, size: pixelSize)
            return PreviewImage(image: nsImage, pixelSize: pixelSize)
        }.value
    }

    // MARK: - Chain read / replace / clear (raw URLSession)

    /// Read the current edit chain for a document.
    func getChain(documentId: String) async throws -> ImageEditChain {
        let url = baseURL.appendingPathComponent("images/\(documentId)/edits")
        var request = URLRequest(url: url)
        request.addEngineAuth(libraryPath: libraryPath)
        let (data, response) = try await session.data(for: request)
        try Self.expectOK(response, data: data)
        return try Self.decodeChain(data, documentId: documentId)
    }

    /// Replace the whole chain (used to remove a single op by re-posting the
    /// survivors — the backend has no per-op delete endpoint).
    @discardableResult
    func setOperations(documentId: String, operations: [AnyCodable]) async throws -> ImageEditChain {
        let url = baseURL.appendingPathComponent("images/\(documentId)/edits")
        var request = URLRequest(url: url)
        request.httpMethod = "PUT"
        request.addEngineAuth(libraryPath: libraryPath)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(ChainUpsertDTO(operations: operations))
        let (data, response) = try await session.data(for: request)
        try Self.expectOK(response, data: data)
        return try Self.decodeChain(data, documentId: documentId)
    }

    /// Remove the operation at `index`, re-posting the remaining ops.
    @discardableResult
    func removeOperation(documentId: String, at index: Int) async throws -> ImageEditChain {
        let chain = try await getChain(documentId: documentId)
        guard chain.operations.indices.contains(index) else { return chain }
        var survivors = chain.operations
        survivors.remove(at: index)
        return try await setOperations(documentId: documentId, operations: survivors.map(\.raw))
    }

    /// Clear all edits (`DELETE /edits`) — the "Reset all edits" affordance.
    func resetChain(documentId: String) async throws {
        let url = baseURL.appendingPathComponent("images/\(documentId)/edits")
        var request = URLRequest(url: url)
        request.httpMethod = "DELETE"
        request.addEngineAuth(libraryPath: libraryPath)
        let (data, response) = try await session.data(for: request)
        try Self.expectOK(response, data: data, allow: [200, 204])
    }

    // MARK: - Operations (typed client)

    @discardableResult
    func crop(documentId: String, left: Int, top: Int, width: Int, height: Int, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true
        defer { isLoading = false }
        let response = try await client.api.cropImageApiImagesDocumentIdOperationsCropPost(
            path: .init(documentId: documentId),
            headers: .init(xFicheroLibraryPath: libraryPath),
            body: .json(.init(left: left, top: top, width: width, height: height, page: page))
        )
        guard case .ok = response else { throw ImageEditingError.operationFailed("crop") }
        return try await getChain(documentId: documentId)
    }

    @discardableResult
    func rotate(documentId: String, angle: Double, expand: Bool = true, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true
        defer { isLoading = false }
        let response = try await client.api.rotateImageApiImagesDocumentIdOperationsRotatePost(
            path: .init(documentId: documentId),
            headers: .init(xFicheroLibraryPath: libraryPath),
            body: .json(.init(angle: angle, expand: expand, page: page))
        )
        guard case .ok = response else { throw ImageEditingError.operationFailed("rotate") }
        return try await getChain(documentId: documentId)
    }

    @discardableResult
    func enhance(
        documentId: String,
        brightness: Double = 1.0,
        contrast: Double = 1.0,
        sharpen: Double = 1.0,
        autoLevels: Bool = false,
        page: Int = 1
    ) async throws -> ImageEditChain {
        isLoading = true
        defer { isLoading = false }
        let response = try await client.api.enhanceImageApiImagesDocumentIdOperationsEnhancePost(
            path: .init(documentId: documentId),
            headers: .init(xFicheroLibraryPath: libraryPath),
            body: .json(.init(
                brightness: brightness,
                contrast: contrast,
                sharpen: sharpen,
                autoLevels: autoLevels,
                page: page
            ))
        )
        guard case .ok = response else { throw ImageEditingError.operationFailed("enhance") }
        return try await getChain(documentId: documentId)
    }

    @discardableResult
    func removeBackground(
        documentId: String,
        method: String = "opencv",
        threshold: Int = 28,
        page: Int = 1
    ) async throws -> ImageEditChain {
        isLoading = true
        defer { isLoading = false }
        let response = try await client.api.removeBackgroundImageApiImagesDocumentIdOperationsRemoveBackgroundPost(
            path: .init(documentId: documentId),
            headers: .init(xFicheroLibraryPath: libraryPath),
            body: .json(.init(method: method, threshold: threshold, page: page))
        )
        guard case .ok = response else { throw ImageEditingError.operationFailed("remove_background") }
        return try await getChain(documentId: documentId)
    }

    @discardableResult
    func segment(
        documentId: String,
        method: String = "foreground",
        threshold: Int = 28,
        minArea: Int = 100,
        maxSegments: Int = 20,
        page: Int = 1
    ) async throws -> ImageEditChain {
        isLoading = true
        defer { isLoading = false }
        let response = try await client.api.segmentImageApiImagesDocumentIdOperationsSegmentPost(
            path: .init(documentId: documentId),
            headers: .init(xFicheroLibraryPath: libraryPath),
            body: .json(.init(
                method: method,
                threshold: threshold,
                minArea: minArea,
                maxSegments: maxSegments,
                page: page
            ))
        )
        guard case .ok = response else { throw ImageEditingError.operationFailed("segment") }
        return try await getChain(documentId: documentId)
    }

    // MARK: - Decoding helpers

    private static func expectOK(_ response: URLResponse, data: Data, allow: Set<Int> = [200]) throws {
        guard let http = response as? HTTPURLResponse else { throw ImageEditingError.invalidResponse }
        guard allow.contains(http.statusCode) else {
            let peek = String(data: data.prefix(200), encoding: .utf8) ?? "<binary>"
            throw ImageEditingError.unexpectedStatus(status: http.statusCode, bodyPeek: peek)
        }
    }

    private static func decodeChain(_ data: Data, documentId: String) throws -> ImageEditChain {
        // 204 / empty body (e.g. after DELETE) -> empty chain.
        guard !data.isEmpty else {
            return ImageEditChain(documentId: documentId, operations: [], updatedAt: nil)
        }
        let dto = try JSONDecoder().decode(ChainResponseDTO.self, from: data)
        let ops = dto.operations.map { ImageEditOperation(raw: $0) }
        let updatedAt = dto.updatedAt.flatMap { ISO8601DateFormatter().date(from: $0) }
        return ImageEditChain(
            documentId: dto.documentId ?? documentId,
            operations: ops,
            updatedAt: updatedAt
        )
    }
}

// MARK: - Supporting types

/// A decoded preview image plus its source pixel dimensions.
struct PreviewImage {
    let image: NSImage
    let pixelSize: CGSize
}

private struct ChainResponseDTO: Decodable {
    let documentId: String?
    let operations: [AnyCodable]
    let updatedAt: String?

    enum CodingKeys: String, CodingKey {
        case documentId = "document_id"
        case operations
        case updatedAt = "updated_at"
    }
}

private struct ChainUpsertDTO: Encodable {
    let operations: [AnyCodable]
}

enum ImageEditingError: Error, LocalizedError {
    case invalidResponse
    case invalidImageData
    case operationFailed(String)
    case unexpectedStatus(status: Int, bodyPeek: String)

    var errorDescription: String? {
        switch self {
        case .invalidResponse:
            return "Invalid response from image-editing service"
        case .invalidImageData:
            return "Could not decode preview image data"
        case .operationFailed(let name):
            return "Image operation failed: \(name)"
        case let .unexpectedStatus(status, peek):
            return "Image-editing HTTP \(status): \(peek)"
        }
    }
}
