@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Items reads its proposals again when ANY Find the Documents run ends (`finddocs.review.items`), a recipe run's
/// step among them, from the jobs read the app already makes: not only the run the menu started. Written from the
/// spec; through the real `ActivityStore` and `FoundDocumentsStore` over a stubbed transport.
private final class RunEndsURLProtocol: URLProtocol {
    nonisolated(unsafe) static var jobsJSON = ""
    nonisolated(unsafe) static var listed: [String] = []

    override static func canInit(with request: URLRequest) -> Bool { true }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url?.path ?? ""
        var status = 404, body = #"{"detail":"not stubbed"}"#
        if path == "/api/activity/jobs" {
            status = 200
            body = Self.jobsJSON
        } else if path == "/api/find-documents/proposals" {
            Self.listed.append(request.url?.query ?? "")
            status = 200
            body = #"{"items":[],"count":0}"#
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct FindDocumentsRunEndsTests {
    private func client() -> FicheroClient {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RunEndsURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/RunEnds.fichero",
                             session: URLSession(configuration: configuration))
    }

    private static func job(_ id: String, kind: String, state: String, parent: String? = nil) -> String {
        let parentField = parent.map { #","parent_id":"\#($0)""# } ?? ""
        return #"{"id":"\#(id)","task_type":"\#(kind)","name":"\#(kind)","library":"","current":0,"total":0,"#
            + #""percent":0,"state":"\#(state)"\#(parentField)}"#
    }

    private static func jobs(_ rows: [String]) -> String {
        #"{"jobs":[\#(rows.joined(separator: ","))],"count":\#(rows.count),"cpu_count":8,"paused":false,"#
            + #""mode":"automatic","machine":{"memory_pressure":"normal","on_battery":false,"in_use":false}}"#
    }

    /// WHY: a recipe run finds the documents as one of its steps; its proposals waited unseen in Items until the
    /// folder was opened again, because only the menu's own run was followed.
    @Test("a recipe run's Find the Documents step leaving the jobs list counts as a run that ended")
    func aRecipeStepEnding() async {
        let store = ActivityStore(service: ActivityService(ficheroClient: client()), library: nil)
        RunEndsURLProtocol.jobsJSON = Self.jobs([
            Self.job("recipe-1", kind: "run-a-recipe", state: "running"),
            Self.job("fd-1", kind: "find-documents-in-a-folder", state: "running", parent: "recipe-1")
        ])
        await store.refreshBackgroundJobs()
        #expect(store.findDocumentsRunsEnded == 0, "still under way")

        RunEndsURLProtocol.jobsJSON = Self.jobs([Self.job("recipe-1", kind: "run-a-recipe", state: "running")])
        await store.refreshBackgroundJobs()
        #expect(store.findDocumentsRunsEnded == 1, "a finished job is not listed: it ended")

        RunEndsURLProtocol.jobsJSON = Self.jobs([])
        await store.refreshBackgroundJobs()
        #expect(store.findDocumentsRunsEnded == 1, "the recipe run ending is not a second Find the Documents run")
    }

    @Test("a run listed as failed has ended too; other kinds of work never count")
    func endedStates() {
        let running = ActivityJob(id: "fd", taskType: ActivityStore.findDocumentsKind, name: "Find", state: .running)
        let failed = ActivityJob(id: "fd", taskType: ActivityStore.findDocumentsKind, name: "Find", state: .failed)
        let embed = ActivityJob(id: "e", taskType: "embed", name: "Embed", state: .running)
        #expect(ActivityStore.aFindDocumentsRunEnded(from: [running], to: [failed]))
        #expect(!ActivityStore.aFindDocumentsRunEnded(from: [running], to: [running]))
        #expect(!ActivityStore.aFindDocumentsRunEnded(from: [failed], to: []), "already ended before")
        #expect(!ActivityStore.aFindDocumentsRunEnded(from: [embed], to: []))
    }

    @Test("reading again reads the shown folder and every folder read so far")
    func readsAgainEveryFolder() async {
        RunEndsURLProtocol.listed = []
        let store = FoundDocumentsStore(client: client())
        await store.load(folderId: "inspected")
        RunEndsURLProtocol.listed = []

        await store.loadAgain(alongWith: "shown")

        #expect(RunEndsURLProtocol.listed.sorted() == ["folder_id=inspected", "folder_id=shown"])
    }
}
