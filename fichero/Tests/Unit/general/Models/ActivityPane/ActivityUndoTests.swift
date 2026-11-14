//
//  ActivityUndoTests.swift — `activity.pane.row-actions-on-the-table` (#6441, #6583): Delete, Archive and Put Back are the
//  audited job actions, each ONE step on the window's stack, so Edit › Undo takes it back through the engine.
//

@testable import Fichero
import Foundation
import Testing

private final class ActivityUndoURLProtocol: URLProtocol {
    struct Seen { let path: String; let body: [String: Any] }
    nonisolated(unsafe) static var seen: [Seen] = []

    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.hasPrefix("/api/actions") || path.hasPrefix("/api/activity")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url?.path ?? ""
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        Self.seen.append(Seen(path: path, body: body))
        let json: String = switch path {
        case "/api/actions/invoke":
            #"{"ok":true,"audit_id":"audit-1","changed_domains":["activity"],"result":{"deleted_ids":["j1","j2"],"skipped_ids":["j3"],"count":2}}"#
        case "/api/actions/audit/undo":
            #"{"ok":true,"audit_ids":["inverse-1"],"results":[],"changed_domains":["activity"]}"#
        default: "{}"
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct ActivityUndoTests {
    private func client() -> FicheroClient {
        ActivityUndoURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ActivityUndoURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/activity-undo.fichero",
                             session: URLSession(configuration: configuration))
    }

    @Test("Delete is the audited job.delete with Stop then Delete, one step named for its rows; Undo takes that row back")
    func deleteIsOneUndoableStep() async throws {
        let client = client()
        let store = ActivityStore(service: ActivityService(ficheroClient: client), library: nil)
        let steps = WindowSteps()
        steps.engineForProject = { _ in nil }  // the step's own service

        let outcome = await store.performUndoable("job.delete", ids: ["j1", "j2", "j3"], stopRunning: true,
                                                  named: "Delete 3 Rows", actions: ActionsService(client: client), steps: steps)

        #expect(outcome == ActivityJobsOutcome(done: 2, skipped: 1))
        let invoke = try #require(ActivityUndoURLProtocol.seen.first { $0.path == "/api/actions/invoke" })
        #expect(invoke.body["name"] as? String == "job.delete")
        let params = invoke.body["params"] as? [String: Any]
        #expect(params?["ids"] as? [String] == ["j1", "j2", "j3"])
        #expect(params?["stop_running"] as? Bool == true)
        #expect(steps.canUndo && steps.undoName == "Delete 3 Rows")

        steps.undo()
        for _ in 0..<500 where !ActivityUndoURLProtocol.seen.contains(where: { $0.path == "/api/actions/audit/undo" }) {
            try await Task.sleep(for: .milliseconds(20))
        }
        let undo = try #require(ActivityUndoURLProtocol.seen.last { $0.path == "/api/actions/audit/undo" })
        #expect(undo.body["audit_ids"] as? [String] == ["audit-1"])
    }

    @Test("Archive and Put Back send their own audited action and no Stop")
    func archiveSendsNoStop() async throws {
        let client = client()
        let store = ActivityStore(service: ActivityService(ficheroClient: client), library: nil)
        _ = await store.performUndoable("job.archive", ids: ["j1"], named: "Archive Row",
                                        actions: ActionsService(client: client), steps: WindowSteps())
        let invoke = try #require(ActivityUndoURLProtocol.seen.first { $0.path == "/api/actions/invoke" })
        #expect(invoke.body["name"] as? String == "job.archive")
        #expect((invoke.body["params"] as? [String: Any])?["stop_running"] == nil)
    }

    @Test("A run's Archive is the engine's run archive, naming its runs, never the runs delete")
    func runArchiveSendsThreadIds() async throws {
        let client = client()
        let store = ActivityStore(service: ActivityService(ficheroClient: client), library: nil)
        _ = await store.performUndoable("workflow_run.archive", ids: ["t1"], named: "Archive Row",
                                        actions: ActionsService(client: client), steps: WindowSteps())
        let invoke = try #require(ActivityUndoURLProtocol.seen.last { $0.path == "/api/actions/invoke" })
        let params = invoke.body["params"] as? [String: Any]
        #expect(invoke.body["name"] as? String == "workflow_run.archive")
        #expect(params?["thread_ids"] as? [String] == ["t1"])
        #expect(params?["ids"] == nil)
    }
}
