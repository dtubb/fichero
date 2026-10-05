//
//  KeepArrangedTests.swift
//  FicheroTests
//
//  Keep arranged, the app half (#5480): setup's fifth way in, and the folder's Inspector switch
//  between Index and Keep arranged. Written from `source.onboard.keep-arranged` and
//  `source.onboard.five-ways-in` (section 7b: "before the first arrangement, setup shows how
//  many files would move and a sample of the new paths, and nothing moves until the person says
//  yes"), not from the code.
//
//  The engine arranges a folder as soon as it is kept arranged (`sync_folder.tie` and
//  `set_mode` queue the first arrangement), so "nothing moves until yes" means: no request that
//  keeps the folder arranged is sent before the yes. Through the real `RecipeSetupStore`,
//  `SyncFolderStore` and `ImportService` over the generated client; only the transport is stubbed.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class ArrangeURLProtocol: URLProtocol {
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
struct KeepArrangedTests {

    private func makeClient(_ handler: @escaping (URLRequest) -> (Int, String)) -> FicheroClient {
        ArrangeURLProtocol.handler = handler
        ArrangeURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [ArrangeURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                             session: URLSession(configuration: configuration))
    }

    private var calls: [String] { ArrangeURLProtocol.seen.map { "\($0.method) \($0.path)" } }

    /// Any request that would keep the folder arranged (and so start moving files).
    private var keepArrangedRequests: [ArrangeURLProtocol.Seen] {
        ArrangeURLProtocol.seen.filter { $0.body["mode"] as? String == "keep-arranged" }
    }

    private static func folderJSON(id: String = "f1", path: String, mode: String = "index") -> String {
        #"{"id":"\#(id)","path":"\#(path)","formats":["pagexml"],"mode":"\#(mode)","intake":false,"#
            + #""conflicts":[],"adopted":true,"last_written":null,"pending":0,"files":[],"in_the_way":[],"#
            + #""changed_outside":[],"taken_in":[],"not_read_back":[],"deleted_outside":[]}"#
    }

    private static func list(_ folders: String...) -> String { #"{"folders":[\#(folders.joined(separator: ","))]}"# }

    /// Five misplaced files, as the engine's dry run lists them (the spec's own test fixture).
    private static let fiveMoves: String = {
        let moves = (1...5).map {
            #"{"document_id":"d\#($0)","from_path":"IMG_000\#($0).jpg","to_path":"Letters/IMG_000\#($0).jpg"}"#
        }
        return #"{"mode":"index","moves":[\#(moves.joined(separator: ","))],"refused":null}"#
    }()

    // MARK: Setup (source.onboard.five-ways-in, source.onboard.keep-arranged)

    /// WHY: Keep arranged was listed as "not available yet" (#5480). Chosen now, Add a Folder…
    /// must import the folder as Index (the folder stays where it is), tie it the same way Index
    /// does, and read the dry run so the screen shows how many files would move and where, all
    /// BEFORE anything is moved: the engine starts arranging the moment a folder is kept
    /// arranged, so no request may say `keep-arranged` until the person presses Arrange. The
    /// yes is the one `PUT …/mode` with `keep-arranged`.
    @Test("setup's Keep arranged ties the folder, shows the dry run, and keeps it arranged only on yes")
    func keepArrangedInSetupShowsDryRunBeforeAnyMove() async throws {
        let folder = FileManager.default.temporaryDirectory.appendingPathComponent("arrange-\(UUID().uuidString)")
        try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        let saved = FolderAccessManager.shared.engineAccessService
        FolderAccessManager.shared.engineAccessService = AcceptingEngine()
        defer {
            FolderAccessManager.shared.engineAccessService = saved
            try? FileManager.default.removeItem(at: folder)
        }
        var mode = "index"
        let client = makeClient { request in
            switch (request.httpMethod ?? "GET", request.url?.path ?? "") {
            case ("POST", "/api/ingest/folder"):
                return (200, #"{"task_id":"t1","status":"pending","path":"\#(folder.path)"}"#)
            case (_, let path) where path.hasPrefix("/api/ingest"):
                return (200, #"{"task_id":"t1","status":"completed","path":"\#(folder.path)","progress":1,"#
                        + #""total":5,"processed":5,"document_ids":["d1","d2","d3","d4","d5"]}"#)
            case ("GET", "/api/sync-folders"):
                // The Index import adopted the folder as it read it.
                return (200, Self.list(Self.folderJSON(path: folder.path, mode: mode)))
            case ("GET", "/api/sync-folders/f1/intake"):
                return (200, #"{"on":false,"would_bring_in":{}}"#)
            case ("GET", "/api/sync-folders/f1/arrangement"):
                return (200, Self.fiveMoves)
            case ("PUT", "/api/sync-folders/f1/mode"):
                mode = ArrangeURLProtocol.seen.last?.body["mode"] as? String ?? mode
                return (200, Self.folderJSON(path: folder.path, mode: mode))
            default:
                return (404, "{}")
            }
        }
        let setup = RecipeSetupStore(client: client)
        let syncFolders = SyncFolderStore(client: client)
        setup.wayIn = .keepArranged
        #expect(setup.ingestMode == .index, "Keep arranged imports as Index: the folder stays where it is")

        await setup.addFolder(folder, importer: ImportService(ficheroClient: client), syncFolders: syncFolders)

        let ingest = try #require(ArrangeURLProtocol.seen.first { $0.path == "/api/ingest/folder" })
        #expect(ingest.body["mode"] as? String == "index")
        #expect(setup.tiedFolderPath == folder.path, "the folder is tied and shown, as Index does")
        #expect(calls.contains("GET /api/sync-folders/f1/arrangement"), "the dry run is read")
        let proposal = KeepArrangedProposal(preview: try #require(syncFolders.proposedArrangements["f1"]))
        #expect(proposal.headline == "5 files would move, inside this folder, to follow the project's folders.")
        #expect(proposal.samples == ["IMG_0001.jpg → Letters/IMG_0001.jpg", "IMG_0002.jpg → Letters/IMG_0002.jpg",
                                     "IMG_0003.jpg → Letters/IMG_0003.jpg"])
        #expect(proposal.canArrange)
        #expect(keepArrangedRequests.isEmpty, "nothing is kept arranged (so nothing moves) before the yes")
        #expect(setup.errorMessage == nil)

        #expect(await syncFolders.confirmKeepArranged("f1"))

        let yes = try #require(keepArrangedRequests.first)
        #expect("\(yes.method) \(yes.path)" == "PUT /api/sync-folders/f1/mode")
        #expect(syncFolders.folders.first?.mode == .keepArranged, "the folder's entry changes in place")
        #expect(syncFolders.proposedArrangements["f1"] == nil, "the proposal goes once answered")
    }

    /// WHY: the choice is saved with the project (`answers.ingest_mode`) and setup reopens on it.
    /// Saved as plain Index, a reopened setup would lose Keep arranged; an unknown word must be
    /// refused, never read as Link.
    @Test("Keep arranged is saved as keep-arranged and read back as Keep arranged")
    func keepArrangedIsSavedAndReadBack() {
        #expect(SetupWayIn.keepArranged.savedName == "keep-arranged")
        #expect(SetupWayIn(savedName: "keep-arranged") == .keepArranged)
        #expect(SetupWayIn(savedName: "INDEX") == .index)
        #expect(SetupWayIn(savedName: "shuffle") == nil)
        #expect(SetupWayIn.allCases.count == 5, "five ways in")
    }

    // MARK: Inspector (source.onboard.keep-arranged)

    /// WHY: switching a folder to Keep arranged in its Inspector must show the same dry run and
    /// wait for Arrange, exactly as setup does; Cancel (choosing Index again) must leave the folder
    /// as it was. A switch that sent the mode at once would move files the person never saw.
    @Test("switching to Keep arranged in the Inspector previews first; Index again cancels")
    func inspectorSwitchPreviewsFirst() async throws {
        let client = makeClient { request in
            switch (request.httpMethod ?? "GET", request.url?.path ?? "") {
            case ("GET", "/api/sync-folders"):
                return (200, Self.list(Self.folderJSON(path: "/Archive/Letters"),
                                       Self.folderJSON(id: "f2", path: "/Archive/Maps")))
            case ("GET", "/api/sync-folders/f1/arrangement"):
                return (200, Self.fiveMoves)
            case ("PUT", "/api/sync-folders/f1/mode"):
                return (200, Self.folderJSON(path: "/Archive/Letters", mode: "keep-arranged"))
            default:
                return (404, "{}")
            }
        }
        let store = SyncFolderStore(client: client)
        await store.load()
        let folder = try #require(store.folders.first { $0.id == "f1" })

        #expect(await store.choose(.keepArranged, for: "f1"))
        #expect(store.shownMode(of: folder) == .keepArranged, "the switch shows the choice with its dry run")
        #expect(store.proposedArrangements["f1"]?.moves.count == 5)
        #expect(keepArrangedRequests.isEmpty, "choosing is not the yes: nothing moves")

        #expect(await store.choose(.index, for: "f1"))
        #expect(store.proposedArrangements["f1"] == nil)
        #expect(store.shownMode(of: folder) == .index)
        #expect(!calls.contains("PUT /api/sync-folders/f1/mode"), "cancelling sends nothing")

        await store.choose(.keepArranged, for: "f1")
        #expect(await store.confirmKeepArranged("f1"))
        #expect(calls.last == "PUT /api/sync-folders/f1/mode")
        #expect(store.folders.first { $0.id == "f1" }?.mode == .keepArranged)
        #expect(store.folders.first { $0.id == "f2" }?.mode == .index, "the other folder is untouched")
    }

    /// WHY: a folder the engine would not arrange (one it cannot write to, or no project folder
    /// came from) must say why in the engine's words and offer no Arrange, so the person is not
    /// asked to say yes to something that would be refused.
    @Test("a refused dry run says why and offers no Arrange")
    func refusedDryRunOffersNoArrange() {
        let preview = Components.Schemas.ArrangementPreview(
            mode: .index, moves: [], refused: "Fichero can't write to /Archive/Letters. Make the folder writable, or keep it as Index.")
        let proposal = KeepArrangedProposal(preview: preview)
        #expect(!proposal.canArrange)
        #expect(proposal.headline.hasPrefix("Fichero can't write to"))
        #expect(proposal.samples.isEmpty)
    }
}
