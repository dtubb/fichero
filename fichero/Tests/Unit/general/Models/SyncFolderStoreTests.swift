//
//  SyncFolderStoreTests.swift
//  FicheroTests
//
//  The app half of synced folders (#5480, #4952): setup's Index ties the folder through
//  `/api/sync-folders`, a folder's Inspector shows it is synced with its intake, and Take In,
//  Leave and Untie reach the right routes. Written from `source.onboard.index-ties-the-folder`,
//  `source.sync.status-in-inspector`, `source.sync.intake-is-opt-in` and
//  `source.sync.untie-leaves-files`, not from the code.
//
//  Through the real `SyncFolderStore`, `RecipeSetupStore` and `ImportService` over the generated
//  client; only the transport is stubbed, with responses shaped as the engine records them.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class SyncFolderURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    struct Seen { let method: String; let path: String; let body: [String: Any] }
    nonisolated(unsafe) static var seen: [Seen] = []

    override static func canInit(with request: URLRequest) -> Bool {
        let path = request.url?.path ?? ""
        return path.hasPrefix("/api/sync-folders") || path.hasPrefix("/api/ingest")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        Self.seen.append(Seen(method: request.httpMethod ?? "GET", path: request.url?.path ?? "", body: body))
        let (status, json) = Self.handler?(request) ?? (404, "{}")
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

private final class AcceptingEngine: EngineAccessGranting {
    func grantAccess(toPath path: String, bookmark: Data) async throws {}
}

@MainActor
@Suite(.serialized)
struct SyncFolderStoreTests {

    private func makeClient(_ handler: @escaping (URLRequest) -> (Int, String)) -> FicheroClient {
        SyncFolderURLProtocol.handler = handler
        SyncFolderURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SyncFolderURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                             session: URLSession(configuration: configuration))
    }

    private var calls: [String] { SyncFolderURLProtocol.seen.map { "\($0.method) \($0.path)" } }

    /// One folder as `GET /api/sync-folders` lists it (`SyncFolderStatus`).
    private static func folderJSON(id: String = "f1", path: String, intake: Bool = false, adopted: Bool = false,
                                   changedOutside: [String] = [], conflicts: [String] = []) -> String {
        let quoted = { (list: [String]) in "[" + list.map { "\"\($0)\"" }.joined(separator: ",") + "]" }
        return #"{"id":"\#(id)","path":"\#(path)","formats":["pagexml"],"intake":\#(intake),"#
            + #""conflicts":\#(quoted(conflicts)),"adopted":\#(adopted),"last_written":null,"pending":0,"#
            + #""files":["letter.xml"],"in_the_way":[],"changed_outside":\#(quoted(changedOutside)),"#
            + #""taken_in":[],"not_read_back":[],"deleted_outside":[]}"#
    }

    private static func list(_ folders: String...) -> String {
        #"{"folders":[\#(folders.joined(separator: ","))]}"#
    }

    private static func intakeJSON(on: Bool, waiting: [String: Int] = [:]) -> String {
        let counts = waiting.map { "\"\($0.key)\":\($0.value)" }.joined(separator: ",")
        return #"{"on":\#(on),"would_bring_in":{\#(counts)}}"#
    }

    private func folderDocument(path: String?) -> Document {
        Document(id: "doc-folder", docType: .folder, name: "Letters", path: path, status: .completed)
    }

    // MARK: source.onboard.index-ties-the-folder

    /// WHY: choosing Index used to record the mode and nothing more (#5480): the app never
    /// called `/api/sync-folders`, so an indexed folder was never kept in step, and its intake
    /// was never shown. Add a Folder… with Index must import the folder as `index` AND tie that
    /// same folder (the POST names its path), then read its intake for the screen to show.
    @Test("Add a Folder… with Index imports the folder and ties it through POST /api/sync-folders")
    func indexTiesTheFolder() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("sync-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let saved = FolderAccessManager.shared.engineAccessService
        FolderAccessManager.shared.engineAccessService = AcceptingEngine()
        defer {
            FolderAccessManager.shared.engineAccessService = saved
            try? FileManager.default.removeItem(at: folder)
        }
        var tied = false
        let client = makeClient { request in
            switch (request.httpMethod ?? "GET", request.url?.path ?? "") {
            case ("POST", "/api/ingest/folder"):
                return (200, #"{"task_id":"t1","status":"pending","path":"\#(folder.path)"}"#)
            case (_, let path) where path.hasPrefix("/api/ingest"):
                return (200, #"{"task_id":"t1","status":"completed","path":"\#(folder.path)","progress":1,"#
                        + #""total":1,"processed":1,"document_ids":["d1"]}"#)
            case ("POST", "/api/sync-folders"):
                tied = true
                return (200, #"{"id":"f1"}"#)
            case ("GET", "/api/sync-folders"):
                return (200, tied ? Self.list(Self.folderJSON(path: folder.path)) : Self.list())
            case ("GET", "/api/sync-folders/f1/intake"):
                return (200, Self.intakeJSON(on: false))
            default:
                return (404, "{}")
            }
        }
        let setup = RecipeSetupStore(client: client)
        let syncFolders = SyncFolderStore(client: client)
        setup.ingestMode = .index

        await setup.addFolder(folder, importer: ImportService(ficheroClient: client), syncFolders: syncFolders)

        let ingest = try #require(SyncFolderURLProtocol.seen.first { $0.path == "/api/ingest/folder" })
        #expect(ingest.body["mode"] as? String == "index")
        let tie = try #require(SyncFolderURLProtocol.seen.first { $0.method == "POST" && $0.path == "/api/sync-folders" })
        #expect(tie.body["path"] as? String == folder.path, "the folder tied is the folder imported")
        #expect((tie.body["formats"] as? [String])?.isEmpty == false, "the engine refuses a tie with no format")
        #expect(calls.contains("GET /api/sync-folders/f1/intake"), "setup reads the intake preview to show it")
        #expect(setup.tiedFolderPath == folder.path)
        #expect(syncFolders.folder(atPath: folder.path)?.id == "f1")
        #expect(setup.errorMessage == nil)
    }

    /// WHY: the engine's Index import adopts its folder as it reads it (kept in its own layout,
    /// written back in place). Posting a tie on top would make a SECOND synced folder writing
    /// Fichero's own layout into the person's folder. A folder already listed is used as it is.
    @Test("a folder the Index import already adopted is not tied a second time")
    func adoptedFolderIsNotTiedAgain() async {
        let client = makeClient { request in
            switch (request.httpMethod ?? "GET", request.url?.path ?? "") {
            case ("GET", "/api/sync-folders"):
                return (200, Self.list(Self.folderJSON(path: "/Archive/Letters", intake: true, adopted: true)))
            case ("GET", "/api/sync-folders/f1/intake"):
                return (200, Self.intakeJSON(on: true))
            default:
                return (500, "{}")
            }
        }
        let store = SyncFolderStore(client: client)

        let tied = await store.tie(path: "/Archive/Letters")

        #expect(tied?.id == "f1")
        #expect(!calls.contains("POST /api/sync-folders"))
        #expect(store.folders.map(\.id) == ["f1"])
    }

    // MARK: source.sync.status-in-inspector, source.sync.intake-is-opt-in

    /// WHY: the folder's Inspector is where a person learns the folder is synced and that files
    /// changed in it wait to come in. If the folder were not found by its place on disk, or the
    /// preview's counts were dropped, the Inspector would say nothing and the edits made outside
    /// would sit unseen.
    @Test("a synced folder's Inspector says it is synced and what waits to come in")
    func inspectorShowsSyncedAndIntake() async throws {
        let client = makeClient { request in
            switch request.url?.path ?? "" {
            case "/api/sync-folders":
                return (200, Self.list(Self.folderJSON(path: "/Archive/Letters", adopted: true,
                                                       changedOutside: ["letter.xml"])))
            case "/api/sync-folders/f1/intake":
                return (200, Self.intakeJSON(on: false, waiting: ["pagexml": 2]))
            default:
                return (404, "{}")
            }
        }
        let store = SyncFolderStore(client: client)
        await store.load()
        let folder = try #require(FolderSyncInspectorSection.syncedFolder(
            for: folderDocument(path: "/Archive/Letters"), in: store))
        await store.fetchIntake(folder.id)

        let summary = SyncedFolderSummary(folder: folder, intake: store.intakeStates[folder.id])
        #expect(summary.kind == "Synced: kept in its own layout")
        #expect(summary.path == "/Archive/Letters")
        #expect(summary.formats == "PAGE XML")
        #expect(summary.intake == "2 files changed in the folder wait to come in (PAGE XML 2)")
        #expect(summary.somethingWaits)
        #expect(summary.notices == ["1 file changed outside Fichero"])
        #expect(store.errorMessage == nil)
    }

    /// WHY: only a folder the project is tied to has a synced section. A folder that is not
    /// synced, or a file, must show nothing: a section there would claim a sync that does not
    /// exist and offer Untie on a folder nothing is tied to.
    @Test("a folder that is not synced, or a file, shows no synced section")
    func unsyncedFolderShowsNothing() async {
        let store = SyncFolderStore(client: makeClient { request in
            request.url?.path == "/api/sync-folders"
                ? (200, Self.list(Self.folderJSON(path: "/Archive/Letters"))) : (404, "{}")
        })
        await store.load()

        #expect(FolderSyncInspectorSection.syncedFolder(for: folderDocument(path: "/Archive/Maps"), in: store) == nil)
        #expect(FolderSyncInspectorSection.syncedFolder(for: folderDocument(path: nil), in: store) == nil)
        let file = Document(id: "doc-file", docType: .file, name: "letter.jpg", path: "/Archive/Letters")
        #expect(FolderSyncInspectorSection.syncedFolder(for: file, in: store) == nil)
    }

    // MARK: Take In, Leave, Untie

    /// WHY: Take In and Leave are the person's yes and no to what changed in the folder. Each
    /// must PUT the folder's own intake route with the right answer, and the folder's state must
    /// change in place, or the buttons would show the old state after the engine changed it.
    @Test("Take In and Leave put the folder's intake on and off, updating it in place")
    func takeInAndLeave() async throws {
        var on = false
        let client = makeClient { request in
            switch (request.httpMethod ?? "GET", request.url?.path ?? "") {
            case ("GET", "/api/sync-folders"):
                return (200, Self.list(Self.folderJSON(path: "/Archive/Letters"),
                                       Self.folderJSON(id: "f2", path: "/Archive/Maps")))
            case ("PUT", "/api/sync-folders/f1/intake"):
                // The body stream is read once, by the stub, before this handler runs.
                on = SyncFolderURLProtocol.seen.last?.body["on"] as? Bool ?? false
                return (200, Self.intakeJSON(on: on))
            default:
                return (404, "{}")
            }
        }
        let store = SyncFolderStore(client: client)
        await store.load()

        #expect(await store.setIntake("f1", on: true))
        let put = try #require(SyncFolderURLProtocol.seen.last)
        #expect("\(put.method) \(put.path)" == "PUT /api/sync-folders/f1/intake")
        #expect(put.body["on"] as? Bool == true)
        #expect(store.folders.first { $0.id == "f1" }?.intake == true)
        #expect(store.folders.first { $0.id == "f2" }?.intake == false, "the other folder is untouched")

        #expect(await store.setIntake("f1", on: false))
        #expect(SyncFolderURLProtocol.seen.last?.body["on"] as? Bool == false)
        #expect(store.folders.first { $0.id == "f1" }?.intake == false)
    }

    /// WHY: Untie must DELETE that folder's route, and the folder must leave the list (so its
    /// Inspector section goes) while the other folders stay where they are.
    @Test("Untie deletes the folder's route and removes only that folder")
    func untie() async {
        let client = makeClient { request in
            switch (request.httpMethod ?? "GET", request.url?.path ?? "") {
            case ("GET", "/api/sync-folders"):
                return (200, Self.list(Self.folderJSON(path: "/Archive/Letters"),
                                       Self.folderJSON(id: "f2", path: "/Archive/Maps")))
            case ("DELETE", "/api/sync-folders/f1"):
                return (200, #"{"id":"f1"}"#)
            default:
                return (404, "{}")
            }
        }
        let store = SyncFolderStore(client: client)
        await store.load()

        #expect(await store.untie("f1"))
        #expect(calls.last == "DELETE /api/sync-folders/f1")
        #expect(store.folders.map(\.id) == ["f2"])
        #expect(store.folder(atPath: "/Archive/Letters") == nil)
    }
}
