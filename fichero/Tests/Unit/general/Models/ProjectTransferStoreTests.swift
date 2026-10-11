//
//  ProjectTransferStoreTests.swift
//  FicheroTests
//
//  A drop onto another project (#2397, #4311, `transfer.app.*`): the store asks the engine's dry run through the
//  TARGET's client, runs the move or copy, updates both projects' stores one item at a time, and puts the step on
//  the window's undo stack under the target's audit row. Driven through the generated client against a stub.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class TransferMockURLProtocol: URLProtocol {
    /// Each request: its path, the project its library header names, and its JSON body.
    struct Seen {
        let path: String
        let library: String
        let body: [String: Any]
    }
    nonisolated(unsafe) static var seen: [Seen] = []
    nonisolated(unsafe) static var transferStatus = 200
    override static func canInit(with request: URLRequest) -> Bool { true }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url?.path ?? ""
        let library = (request.value(forHTTPHeaderField: "X-Fichero-Library-Path") ?? "").removingPercentEncoding ?? ""
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        Self.seen.append(Seen(path: path, library: library, body: body))
        let (status, json) = Self.answer(path: path, body: body)
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}

    private static func answer(path: String, body: [String: Any]) -> (Int, String) {
        switch path {
        case "/api/documents/transfer":
            if transferStatus != 200 {
                return (transferStatus, #"{"detail":"These items are already being moved to Istmina."}"#)
            }
            let dryRun = body["dry_run"] as? Bool ?? false
            let mode = body["mode"] as? String ?? "copy"
            return (200, """
            {"transfer_id":"t1","mode":"\(mode)","dry_run":\(dryRun),"state":"\(dryRun ? "planned" : "done")",
             "source":"/tmp/Marshall.fichero","target":"/tmp/Istmina.fichero","target_parent_id":"sources",
             "actor":"owner","counts":[{"kind":"Document","planned":2},{"kind":"Segment","planned":40},
             {"kind":"Artifact","planned":0}],"files":1,"bytes":2048,
             "cuts":[{"kind":"TypedLink","row":"l1","field":"to_id","points_to":"p9","name":"Letter to Lima",
                      "reason":"its other end stays in Marshall"}],
             "proposals":[{"carried_entity":"e1","name":"Juan de la Cruz","entity_type":"person",
                           "target_entity":"e7","target_name":"Juan de la Cruz","reason":"same name and type"}],
             "copies":\(dryRun ? "[]" : #"["new-1"]"#),"audit":\(dryRun ? "null" : #""audit-9""#)}
            """)
        case "/api/documents":
            return (200, #"{"count":1,"items":[{"id":"new-1","name":"Diary 1933","#
                + #""expected_thumbnail_path":"","expected_display_path":""}]}"#)
        case "/api/actions/audit/audit-9/undo":
            return (200, #"{"ok":true,"result":{},"audit_id":"audit-10","changed_domains":["document"]}"#)
        default:
            return (404, #"{"detail":"not stubbed"}"#)
        }
    }
}

@MainActor
@Suite(.serialized)
struct ProjectTransferStoreTests {
    private func projects() -> (source: LibraryManager.LibraryReference, target: LibraryManager.LibraryReference) {
        TransferMockURLProtocol.seen = []
        TransferMockURLProtocol.transferStatus = 200
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [TransferMockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let source = LibraryManager.LibraryReference(
            url: URL(fileURLWithPath: "/tmp/Marshall.fichero"), document: FicheroDocument(),
            displayName: "Marshall", session: session)
        let target = LibraryManager.LibraryReference(
            url: URL(fileURLWithPath: "/tmp/Istmina.fichero"), document: FicheroDocument(),
            displayName: "Istmina", session: session)
        source.documentStore.currentDocuments = [Document(id: "d1", name: "Diary 1933")]
        target.documentStore.currentDocuments = [Document(id: "f1", name: "Box 4")]
        return (source, target)
    }

    private func transfers() -> [[String: Any]] {
        TransferMockURLProtocol.seen.filter { $0.path == "/api/documents/transfer" }.map(\.body)
    }

    /// WHY (#2397): a drop onto another project's folder used to send the source's id to the target's own move
    /// route, which did not know it, and nothing happened. The drop must ask the engine's transfer, through the
    /// TARGET's client (its library header) with the source named in the body, and plan before it runs.
    @Test("a drag across projects plans a move through the target, then moves: copies in, originals out")
    func aDragMoves() async throws {
        let (source, target) = projects()
        let store = ProjectTransferStore()
        #expect(store.beginIfAcrossProjects(prefixedIds: ["doc:d1"], operation: .move, into: target,
                                            parentId: "f1", openLibraries: [source, target]))
        // The hook starts the dry run in a Task; a request through the test host can take seconds, so wait for its
        // answer (a plan or a refusal), up to 20 s.
        for _ in 0..<2000 where store.pending?.plan == nil && store.pending?.refusal == nil {
            try await Task.sleep(nanoseconds: 10_000_000)
        }

        let plan = try #require(store.pending?.plan, "refused: \(store.pending?.refusal ?? "no answer in 20 s")")
        #expect(transfers().last?["dry_run"] as? Bool == true)
        #expect(transfers().last?["mode"] as? String == "move")
        #expect(transfers().last?["source"] as? String == "/tmp/Marshall.fichero")
        #expect(transfers().last?["items"] as? [String] == ["d1"])
        #expect(transfers().last?["target_parent_id"] as? String == "f1")
        #expect(TransferMockURLProtocol.seen.first { $0.path == "/api/documents/transfer" }?.library
                == "/tmp/Istmina.fichero", "the library header names the target")
        #expect(ProjectTransferStore.whatGoes(plan) == ["2 Document", "40 Segment", "1 file (2 KB)"])
        #expect(ProjectTransferStore.cuts(plan) == ["Letter to Lima: its other end stays in Marshall"])
        #expect(ProjectTransferStore.proposals(plan) == ["Juan de la Cruz may be Juan de la Cruz (same name and type)"])

        await store.run(undoManager: nil)
        #expect(transfers().last?["dry_run"] as? Bool == false)
        let drop = try #require(store.pending)
        let result = try #require(drop.result)
        #expect(ProjectTransferStore.resultWords(result, of: drop).hasPrefix("Moved 1 item to Istmina."))
        #expect(source.documentStore.currentDocuments.isEmpty, "the moved item leaves the source, in place")
        #expect(TransferMockURLProtocol.seen.contains { $0.path == "/api/documents" && $0.library == "/tmp/Istmina.fichero" },
                "the copies are read back from the target, by id, to splice in place")
    }

    /// WHY (`transfer.app.drag-sidebar`): ⌥ is a copy between projects, as in the Finder; the source keeps it.
    @Test("an ⌥-drag copies, and the source keeps its item")
    func anOptionDragCopies() async throws {
        let (source, target) = projects()
        let store = ProjectTransferStore()
        await store.begin(items: ["d1"], from: source, to: target, parentId: nil, decision: .copy)
        #expect(transfers().last?["mode"] as? String == "copy")
        #expect(transfers().last?["target_parent_id"] == nil, "no folder: the target's Sources folder")
        await store.run(undoManager: nil)
        #expect(store.pending?.result != nil)
        #expect(source.documentStore.currentDocuments.map(\.id) == ["d1"], "a copy leaves the source as it was")
    }

    /// WHY (`transfer.alias.not-between-projects`): an alias in another project would dangle; ⌘⌥ is refused in
    /// words before anything is asked of the engine, and Copy is offered instead.
    @Test("⌘⌥ across projects is refused in words, nothing sent; Copy Instead plans a copy")
    func anAliasIsRefused() async throws {
        let (source, target) = projects()
        let store = ProjectTransferStore()
        await store.begin(items: ["d1"], from: source, to: target, parentId: nil, decision: .refuseAlias)
        #expect(store.pending?.refusal == "Aliases stay within a project.")
        #expect(store.pending?.offersCopyInstead == true)
        #expect(transfers().isEmpty, "nothing asked of the engine")
        await store.run(undoManager: nil)
        #expect(transfers().isEmpty, "a refused drop never runs")

        await store.copyInstead()
        #expect(transfers().last?["mode"] as? String == "copy")
        #expect(store.pending?.refusal == nil && store.pending?.plan != nil)
    }

    /// WHY (`transfer.action.refusals-in-words`): a refusal (a second drag, a locked node, a project closed) must
    /// show the engine's own sentence, and nothing may run after it.
    @Test("an engine refusal shows the engine's sentence and nothing runs")
    func aRefusalShowsTheEnginesSentence() async {
        let (source, target) = projects()
        TransferMockURLProtocol.transferStatus = 409
        let store = ProjectTransferStore()
        await store.begin(items: ["d1"], from: source, to: target, parentId: nil, decision: .move)
        #expect(store.pending?.refusal == "These items are already being moved to Istmina.")
        #expect(store.pending?.plan == nil)
        await store.run(undoManager: nil)
        #expect(transfers().count == 1, "only the dry run was asked")
        #expect(source.documentStore.currentDocuments.map(\.id) == ["d1"])
    }

    /// WHY (`transfer.app.drop-checks-project`): only a drop of ANOTHER project's items is a transfer; the
    /// target's own items keep today's move, copy and alias.
    @Test("a drop of the project's own items is not a transfer")
    func ownItemsAreNotATransfer() {
        let (source, target) = projects()
        let store = ProjectTransferStore()
        #expect(!store.beginIfAcrossProjects(prefixedIds: ["doc:f1"], operation: .move, into: target,
                                             parentId: nil, openLibraries: [source, target]))
        #expect(ProjectTransferStore.sourceProject(of: ["unknown"], target: target, among: [source, target]) == nil)
        #expect(ProjectTransferStore.sourceProject(of: ["d1"], target: target, among: [source, target])?.id == source.id)
        #expect(store.pending == nil)
    }

    /// WHY (`transfer.app.undo-both-windows`): ⌘Z right after a transfer takes it back, by the target's audit row
    /// the result names, through the target's project.
    @Test("⌘Z after a move undoes the target's audit row, through the target")
    func undoTakesItBack() async throws {
        let (source, target) = projects()
        let store = ProjectTransferStore()
        let manager = UndoManager()
        manager.groupsByEvent = false
        await store.begin(items: ["d1"], from: source, to: target, parentId: "f1", decision: .move)
        manager.beginUndoGrouping()
        await store.run(undoManager: manager)
        manager.endUndoGrouping()
        #expect(manager.canUndo)
        #expect(manager.undoActionName == "Move to Istmina")

        manager.undo()
        // The undo is an engine call ActionUndo starts in a Task; wait for it to reach the stub, up to 20 s.
        for _ in 0..<2000 where !TransferMockURLProtocol.seen.contains(where: { $0.path.hasSuffix("/undo") }) {
            try await Task.sleep(nanoseconds: 10_000_000)
        }
        let undo = try #require(TransferMockURLProtocol.seen.first { $0.path.hasSuffix("/undo") },
                                "requests seen: \(TransferMockURLProtocol.seen.map(\.path))")
        #expect(undo.path == "/api/actions/audit/audit-9/undo")
        #expect(undo.library == "/tmp/Istmina.fichero")
    }
}
