@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class ICloudMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var replies: [String: String] = [:]
    nonisolated(unsafe) static var bodies: [String: [String: Any]] = [:]
    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path == "/api/documents/in-icloud" || path == "/api/actions/invoke"
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let key = "\(request.httpMethod ?? "GET") \(request.url?.path ?? "")"
        var data = request.httpBody ?? Data()
        if let stream = request.httpBodyStream {
            stream.open()
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let read = stream.read(&buffer, maxLength: buffer.count)
                if read <= 0 { break }
                data.append(buffer, count: read)
            }
            stream.close()
        }
        Self.bodies[key] = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        let response = HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data((Self.replies[key] ?? "null").utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

/// Pages in iCloud (#5669, Daniel's ruling): before Start and when material is added, "N pages are in iCloud and
/// not on this Mac", with Copy into the Project, the engine's undoable action.
@MainActor
@Suite(.serialized)
struct ICloudPagesStoreTests {
    private static let inICloud = """
    {"pages": 34, "of": 92, "bytes": 1200000000, "sentence": "34 of 92 pages are in iCloud and not on this Mac.",
     "room": true, "offer": "Copy them into the project (1.2 GB, then they stay here)",
     "action": "document.copy_into_project", "params": {"ids": ["p1", "p2"]}}
    """

    private func store() -> ICloudPagesStore {
        ICloudMockURLProtocol.bodies = [:]
        ICloudMockURLProtocol.replies = [
            "GET /api/documents/in-icloud": Self.inICloud,
            "POST /api/actions/invoke": #"{"ok": true, "audit_id": "audit-7", "changed_domains": ["document"]}"#
        ]
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ICloudMockURLProtocol.self]
        return ICloudPagesStore(client: FicheroClient(baseURL: URL(string: "https://test.fichero")!,
                                                      libraryPath: "/tmp/test.fichero",
                                                      session: URLSession(configuration: configuration)))
    }

    @Test("what is in iCloud is said with the engine's sentence and offer")
    func saysWhatIsInICloud() async {
        let store = store()
        await store.load()
        #expect(store.pages?.sentence == "34 of 92 pages are in iCloud and not on this Mac.")
        #expect(store.pages?.offer == "Copy them into the project (1.2 GB, then they stay here)")
        #expect(store.canCopy)
    }

    @Test("Ready takes it from the Start plan's in_icloud")
    func readyTakesItFromThePlan() throws {
        let plan = try JSONDecoder().decode(Components.Schemas.StartPlan.self, from: Data("""
        {"runs":[],"skipped":[],"workflows":[],"offered":[],"refusals":[],
         "estimate":{"pages":92,"runs":[],"total_cost_usd":0}, "in_icloud": \(Self.inICloud)}
        """.utf8))
        let store = store()
        store.adopt(fromPlan: plan)
        #expect(store.pages?.pages == 34 && store.pages?.of == 92)
    }

    @Test("Copy into the Project runs the engine's action with its params, then reads again")
    func copyIsTheEnginesAction() async throws {
        let store = store()
        await store.load()
        #expect(await store.copyIntoProject(actionsService: ActionsService(client: store.client), steps: nil))
        let body = try #require(ICloudMockURLProtocol.bodies["POST /api/actions/invoke"])
        #expect(body["name"] as? String == "document.copy_into_project")
        #expect((body["params"] as? [String: Any])?["ids"] as? [String] == ["p1", "p2"])
        #expect(store.copied?.hasPrefix("Copied 34 pages") == true)
    }

    @Test("without room on this disk nothing is offered")
    func noRoomNoOffer() async throws {
        let store = store()
        ICloudMockURLProtocol.replies["GET /api/documents/in-icloud"] = Self.inICloud
            .replacingOccurrences(of: "\"room\": true", with: "\"room\": false, \"refusal\": \"Needs 1.2 GB; 0.4 GB free\"")
        await store.load()
        #expect(store.pages?.room == false)
        #expect(!store.canCopy)
        #expect(!(await store.copyIntoProject(actionsService: ActionsService(client: store.client), steps: nil)))
    }
}
