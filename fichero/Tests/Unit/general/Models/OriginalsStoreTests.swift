@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class OriginalsMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var replies: [String: String] = [:]
    nonisolated(unsafe) static var bodies: [String: [String: Any]] = [:]
    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.hasPrefix("/api/documents/") || path == "/api/actions/invoke"
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let key = "\(request.httpMethod ?? "GET") \(request.url?.path ?? "")"
        if let stream = request.httpBodyStream {
            stream.open()
            var data = Data()
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
                let read = stream.read(&buffer, maxLength: buffer.count)
                if read <= 0 { break }
                data.append(buffer, count: read)
            }
            stream.close()
            Self.bodies[key] = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        } else if let data = request.httpBody {
            Self.bodies[key] = (try? JSONSerialization.jsonObject(with: data)) as? [String: Any]
        }
        let json = Self.replies[key] ?? "null"
        let response = HTTPURLResponse(
            url: request.url!, statusCode: 200, httpVersion: nil, headerFields: ["Content-Type": "application/json"]
        )!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

/// Locate Originals (#5672): Daniel moved his files to "~/Fichero Test Corpus/Colombia". The missing originals are
/// said plainly, the folder chosen gets the engine's plan in words, and Relink is the audited, undoable action.
@MainActor
@Suite(.serialized)
struct OriginalsStoreTests {
    private static let missing = """
    {"pages": 92, "folders": ["/Users/ana/Documents/Colombia/CACIQUES"], "ids": ["p1", "p2"],
     "sentence": "92 pages' originals are not where the project says."}
    """
    private static let plan = """
    {"new_root": "/Users/ana/Fichero Test Corpus/Colombia",
     "matched": [{"id": "p1", "name": "f. 1r.jpg", "from": "/old/f. 1r.jpg", "to": "/new/f. 1r.jpg", "by": "path"}],
     "not_found": [{"id": "p3", "name": "f. 3r.jpg", "from": "/old/f. 3r.jpg"}],
     "ambiguous": [{"id": "p2", "name": "f. 2r.jpg", "from": "/old/f. 2r.jpg", "why": "two files of that name and size",
                    "candidates": ["/new/a/f. 2r.jpg", "/new/b/f. 2r.jpg"]}],
     "folders": [{"id": "caciques", "name": "CACIQUES", "from": "/old"}],
     "sentence": "1 matched, 1 not found, 1 ambiguous."}
    """

    private func store() -> OriginalsStore {
        OriginalsMockURLProtocol.bodies = [:]
        OriginalsMockURLProtocol.replies = [
            "GET /api/documents/missing-originals": Self.missing,
            "POST /api/documents/relink-originals/plan": Self.plan,
            "POST /api/actions/invoke": #"{"ok": true, "audit_id": "audit-1", "changed_domains": ["document"]}"#
        ]
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [OriginalsMockURLProtocol.self]
        let client = FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                                   session: URLSession(configuration: configuration))
        let store = OriginalsStore(client: client)
        store.grant = { _ in }
        return store
    }

    @Test("the missing originals are read, and a page knows its own is missing")
    func missingIsSaid() async {
        let store = store()
        await store.loadMissing()
        #expect(store.missing?.pages == 92)
        #expect(store.isMissing("p1") && !store.isMissing("p9"))
    }

    @Test("the folder chosen gets the engine's plan in words, and nothing is written")
    func planInWords() async throws {
        let store = store()
        await store.choose(URL(fileURLWithPath: "/Users/ana/Fichero Test Corpus/Colombia"))
        let plan = try #require(store.plan)
        #expect(OriginalsStore.lines(of: plan) == [
            "1 matched, 1 not found, 1 ambiguous.",
            "Relinked to the new place: 1.",
            "Not found there, left as they are: 1.",
            "More than one file matches, left for you: 1.",
            "Folders that move with them: 1."
        ])
        #expect(OriginalsMockURLProtocol.bodies["POST /api/documents/relink-originals/plan"]?["new_root"] as? String
                == "/Users/ana/Fichero Test Corpus/Colombia")
        #expect(OriginalsMockURLProtocol.bodies["POST /api/actions/invoke"] == nil, "a plan writes nothing")
    }

    @Test("Relink is the audited, undoable document.relink_originals action, and the missing are read again")
    func relinkIsTheAction() async throws {
        let store = store()
        await store.choose(URL(fileURLWithPath: "/Users/ana/Fichero Test Corpus/Colombia"))
        let actions = ActionsService(client: store.client)
        #expect(await store.relink(actionsService: actions, steps: nil))
        let body = try #require(OriginalsMockURLProtocol.bodies["POST /api/actions/invoke"])
        #expect(body["name"] as? String == "document.relink_originals")
        #expect((body["params"] as? [String: Any])?["new_root"] as? String == "/Users/ana/Fichero Test Corpus/Colombia")
        #expect(store.plan == nil, "the plan is spent")
        #expect(store.missing != nil, "read again after the relink")
    }

    @Test("Relink waits for a plan with something matched")
    func relinkNeedsAMatch() async {
        let store = store()
        #expect(!(await store.relink(actionsService: ActionsService(client: store.client), steps: nil)))
    }
}
