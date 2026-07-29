#if os(macOS)
import XCTest
import Foundation
import HTTPTypes
import OpenAPIRuntime
@testable import FicheroAPIClient

/// The Swift half of the transport round-trip matrix (#4245): prove the
/// `.inMemory` PythonKit transport carries a REAL WORKFLOW, not just a health
/// probe. This is the acceptance test for the transport nobody was sure
/// worked — the same round-trip set the Python matrix
/// (fichero-server/tests/integration/test_transport_matrix.py) runs over UDS
/// and HTTPS:
///
///     health          -> 200 healthy
///     library create  -> a fresh .fichero package via the engine
///     registry        -> the known-library roots list
///     ingest          -> a tiny .txt (searchable) and .png (renderable)
///     search          -> full-text hit on the ingested text
///     thumbnail       -> image bytes for the ingested picture
///
/// Requests go through `InMemoryASGIClientTransport` — the real PythonKit /
/// AsgiBridge / GIL machinery with real JSON and binary bodies — rather than
/// the generated typed client, so this file stays valid across OpenAPI regens
/// (typed-surface coverage lives in InMemoryTransportSmokeTests). Runs under
/// plain `swift test`; `scripts/gate transport` includes it in its filter.
///
/// NOTE: CPython boots ONCE per process and cannot be torn down, so this
/// suite must run in a test process that does no other PythonKit work.
@MainActor
final class TransportMatrixRoundTripTests: XCTestCase {

    override func setUp() async throws {
        try InMemoryTestEnv.configureOrSkip()
    }

    private func send(
        _ method: HTTPRequest.Method,
        _ path: String,
        json: [String: Any]? = nil,
        headers: [(String, String)] = []
    ) async throws -> (status: Int, body: Data) {
        let transport = InMemoryASGIClientTransport(app: InMemoryEngineApp.shared())
        var request = HTTPRequest(method: method, scheme: nil, authority: nil, path: path)
        request.headerFields[.accept] = "application/json"
        var body: HTTPBody?
        if let json {
            request.headerFields[.contentType] = "application/json"
            body = HTTPBody(try JSONSerialization.data(withJSONObject: json))
        }
        for (name, value) in headers {
            if let field = HTTPField.Name(name) { request.headerFields[field] = value }
        }
        let (response, responseBody) = try await transport.send(
            request, body: body,
            baseURL: URL(string: "http://asgi.local")!,
            operationID: "matrixRoundTrip.\(path)"
        )
        var bytes = Data()
        if let responseBody { for try await chunk in responseBody { bytes.append(contentsOf: chunk) } }
        return (response.status.code, bytes)
    }

    private func jsonObject(_ data: Data) -> [String: Any] {
        (try? JSONSerialization.jsonObject(with: data) as? [String: Any]) ?? [:]
    }

    /// One 1x1 transparent PNG — enough for the thumbnail pipeline.
    private static let onePixelPNG = Data(base64Encoded:
        "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j5tQAAAAASUVORK5CYII=")!

    func testInMemoryTransportCarriesTheFullRoundTrip() async throws {
        // 1. health — the transport reaches the in-process engine at all.
        let health = try await send(.get, "/api/health")
        XCTAssertEqual(health.status, 200, "in-process /api/health must be 200")

        // Working area in the OS temp dir (an allowed engine root).
        let work = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-swift-matrix-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: work, withIntermediateDirectories: true)
        defer { try? FileManager.default.removeItem(at: work) }

        // 2. library create + the engine's known-library roots.
        let library = work.appendingPathComponent("Matrix.fichero").path
        let created = try await send(.post, "/api/library", json: ["path": library])
        XCTAssertEqual(created.status, 200,
                       "library create failed: \(String(decoding: created.body, as: UTF8.self))")
        let registry = try await send(.get, "/api/registry")
        XCTAssertEqual(registry.status, 200,
                       "registry failed: \(String(decoding: registry.body, as: UTF8.self))")

        let libraryHeader = [("X-Fichero-Library-Path", library)]

        // 3. ingest a tiny searchable text file and a tiny image.
        let txt = work.appendingPathComponent("matrix-note.txt")
        try Data("the quetzal perched on the transport matrix fixture".utf8).write(to: txt)
        let png = work.appendingPathComponent("matrix-pixel.png")
        try Self.onePixelPNG.write(to: png)

        var documentIds: [String: String] = [:]
        for file in [txt, png] {
            let ingest = try await send(
                .post, "/api/ingest/file",
                json: ["path": file.path, "copy_mode": true, "auto_embed": true],
                headers: libraryHeader
            )
            XCTAssertEqual(ingest.status, 200,
                           "ingest \(file.lastPathComponent) failed: \(String(decoding: ingest.body, as: UTF8.self))")
            let document = jsonObject(ingest.body)
            let id = document["id"] as? String
            XCTAssertNotNil(id, "ingest returned no document id for \(file.lastPathComponent)")
            documentIds[file.pathExtension] = id
        }

        // 4. full-text search finds the ingested text document.
        let search = try await send(
            .post, "/api/search",
            json: ["query": "quetzal", "search_type": "fulltext", "min_score": 0.0],
            headers: libraryHeader
        )
        XCTAssertEqual(search.status, 200,
                       "search failed: \(String(decoding: search.body, as: UTF8.self))")
        let hits = (jsonObject(search.body)["results"] as? [[String: Any]] ?? [])
            .compactMap { $0["document_id"] as? String }
        XCTAssertTrue(
            hits.contains(documentIds["txt"] ?? "<missing>"),
            "the ingested text document was not a search hit over .inMemory; got \(hits)"
        )

        // 5. thumbnail bytes for the image document (generated on demand) —
        //    a BINARY response through the ASGI bridge, not just JSON.
        let thumb = try await send(
            .get, "/api/storage/thumbnail/\(documentIds["png"] ?? "<missing>")",
            headers: libraryHeader
        )
        XCTAssertEqual(thumb.status, 200,
                       "thumbnail failed: \(String(decoding: thumb.body, as: UTF8.self).prefix(200))")
        XCTAssertGreaterThan(thumb.body.count, 0, "thumbnail body is empty")
    }
}
#endif
