import AppKit
import Foundation
import ImageIO
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
/// All URL paths are written with the full `/api/images/...` prefix in source
/// so `scripts/check_ui_wiring.py` can confirm every endpoint is called from
/// hand-written Swift (the scanner does a regex search over source text).
///
/// The five operation POSTs (crop/rotate/enhance/remove-background/segment)
/// use raw `URLSession` so the path strings are visible. Chain CRUD and preview
/// also use raw `URLSession` — no dependency on the generated typed client.
@MainActor
final class ImageEditingServiceGenerated: ObservableObject {
    @Published var isLoading: Bool = false
    @Published var lastError: Error?

    private let libraryPath: String
    private let engineURL: URL
    private let session = URLSession.shared

    /// - Parameter engineURL: Engine root without `/api` (e.g. `http://127.0.0.1:8765`).
    init(libraryPath: String, engineURL: URL = URL(string: "http://127.0.0.1:8765")!) {
        self.libraryPath = libraryPath
        self.engineURL = engineURL
    }

    convenience init(apiClient: APIClient) {
        // Strip /api from apiClient.baseURL to get the engine root so all
        // path strings can start with /api/... and be scanner-visible.
        self.init(
            libraryPath: apiClient.currentLibraryPath ?? "",
            engineURL: apiClient.baseURL.deletingLastPathComponent()
        )
    }

    // MARK: - URL helpers

    /// Build a URL from a full /api/... path string. The path starts with /api/
    /// so the wiring scanner regex can detect every endpoint in source.
    private func url(for path: String) -> URL {
        var comps = URLComponents(url: engineURL, resolvingAgainstBaseURL: false)!
        comps.path = path
        return comps.url!
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
        var request = URLRequest(url: previewURL(documentId: documentId, applyEdits: applyEdits, page: page))
        request.addEngineAuth(libraryPath: libraryPath)
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw ImageEditingError.invalidResponse }
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
            return PreviewImage(image: NSImage(cgImage: cgImage, size: pixelSize), pixelSize: pixelSize)
        }.value
    }

    // MARK: - Chain read / replace / clear  (GET /api/images/{id}/edits, PUT, DELETE)

    func getChain(documentId: String) async throws -> ImageEditChain {
        var request = URLRequest(url: url(for: "/api/images/\(documentId)/edits"))
        request.addEngineAuth(libraryPath: libraryPath)
        let (data, response) = try await session.data(for: request)
        try Self.expectOK(response, data: data)
        return try Self.decodeChain(data, documentId: documentId)
    }

    @discardableResult
    func setOperations(documentId: String, operations: [AnyCodable]) async throws -> ImageEditChain {
        var request = URLRequest(url: url(for: "/api/images/\(documentId)/edits"))
        request.httpMethod = "PUT"
        request.addEngineAuth(libraryPath: libraryPath)
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(ChainUpsertDTO(operations: operations))
        let (data, response) = try await session.data(for: request)
        try Self.expectOK(response, data: data)
        return try Self.decodeChain(data, documentId: documentId)
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
        var request = URLRequest(url: url(for: "/api/images/\(documentId)/edits"))
        request.httpMethod = "DELETE"
        request.addEngineAuth(libraryPath: libraryPath)
        let (data, response) = try await session.data(for: request)
        try Self.expectOK(response, data: data, allow: [200, 204])
    }

    // MARK: - Operations  (POST /api/images/{id}/operations/*)

    @discardableResult
    func crop(documentId: String, left: Int, top: Int, width: Int, height: Int, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        struct Body: Encodable { let left, top, width, height, page: Int }
        return try await postOp(path: "/api/images/\(documentId)/operations/crop",
                                body: Body(left: left, top: top, width: width, height: height, page: page),
                                documentId: documentId)
    }

    @discardableResult
    func rotate(documentId: String, angle: Double, expand: Bool = true, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        struct Body: Encodable { let angle: Double; let expand: Bool; let page: Int }
        return try await postOp(path: "/api/images/\(documentId)/operations/rotate",
                                body: Body(angle: angle, expand: expand, page: page),
                                documentId: documentId)
    }

    @discardableResult
    func enhance(documentId: String, brightness: Double = 1.0, contrast: Double = 1.0,
                 sharpen: Double = 1.0, autoLevels: Bool = false, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        struct Body: Encodable {
            let brightness, contrast, sharpen: Double; let page: Int; let autoLevels: Bool
            enum CodingKeys: String, CodingKey {
                case brightness, contrast, sharpen, page
                case autoLevels = "auto_levels"
            }
        }
        return try await postOp(path: "/api/images/\(documentId)/operations/enhance",
                                body: Body(brightness: brightness, contrast: contrast,
                                           sharpen: sharpen, page: page, autoLevels: autoLevels),
                                documentId: documentId)
    }

    @discardableResult
    func removeBackground(documentId: String,
                          method: String = "opencv",
                          threshold: Int = 28,
                          page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        struct Body: Encodable { let method: String; let threshold, page: Int }
        return try await postOp(path: "/api/images/\(documentId)/operations/remove-background",
                                body: Body(method: method, threshold: threshold, page: page),
                                documentId: documentId)
    }

    @discardableResult
    func segment(documentId: String, method: String = "foreground", threshold: Int = 28,
                 minArea: Int = 100, maxSegments: Int = 20, page: Int = 1) async throws -> ImageEditChain {
        isLoading = true; defer { isLoading = false }
        struct Body: Encodable {
            let method: String; let threshold, page, minArea, maxSegments: Int
            enum CodingKeys: String, CodingKey {
                case method, threshold, page
                case minArea = "min_area"
                case maxSegments = "max_segments"
            }
        }
        return try await postOp(path: "/api/images/\(documentId)/operations/segment",
                                body: Body(method: method, threshold: threshold, page: page,
                                           minArea: minArea, maxSegments: maxSegments),
                                documentId: documentId)
    }

    // MARK: - Shared POST helper

    private func postOp<T: Encodable>(path: String, body: T, documentId: String) async throws -> ImageEditChain {
        var req = URLRequest(url: url(for: path))
        req.httpMethod = "POST"
        req.addEngineAuth(libraryPath: libraryPath)
        req.setValue("application/json", forHTTPHeaderField: "Content-Type")
        req.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await session.data(for: req)
        try Self.expectOK(response, data: data)
        return try Self.decodeChain(data, documentId: documentId)
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
        guard !data.isEmpty else {
            return ImageEditChain(documentId: documentId, operations: [], updatedAt: nil)
        }
        let dto = try JSONDecoder().decode(ChainResponseDTO.self, from: data)
        let ops = dto.operations.map { ImageEditOperation(raw: $0) }
        let updatedAt = dto.updatedAt.flatMap { ISO8601DateFormatter().date(from: $0) }
        return ImageEditChain(documentId: dto.documentId ?? documentId, operations: ops, updatedAt: updatedAt)
    }
}

// MARK: - Supporting types

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
        case .invalidResponse: return "Invalid response from image-editing service"
        case .invalidImageData: return "Could not decode preview image data"
        case .operationFailed(let name): return "Image operation failed: \(name)"
        case let .unexpectedStatus(status, peek): return "Image-editing HTTP \(status): \(peek)"
        }
    }
}
