//
//  KeptExportStoreTests.swift
//  FicheroTests
//
//  Kept exported, the app half (#5485): setup's screen 3 and the project Inspector's list.
//  Written from `source.onboard.kept-exported` and section 7b, screen 3 ("one row per export:
//  the folder, the format, and one file per page or per document"; the page formats are per
//  page only; removing keeps the files), not from the code.
//
//  Through the real `KeptExportStore` over the generated client; only the transport is stubbed,
//  with responses shaped as `/api/export/kept` answers.
//

@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class KeptExportURLProtocol: URLProtocol {
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    struct Seen { let method: String; let path: String; let body: [String: Any] }
    nonisolated(unsafe) static var seen: [Seen] = []

    override static func canInit(with request: URLRequest) -> Bool {
        request.url?.path.hasPrefix("/api/export/kept") ?? false
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

@MainActor
@Suite(.serialized)
struct KeptExportStoreTests {

    private func makeClient(_ handler: @escaping (URLRequest) -> (Int, String)) -> FicheroClient {
        KeptExportURLProtocol.handler = handler
        KeptExportURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [KeptExportURLProtocol.self]
        return FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                             session: URLSession(configuration: configuration))
    }

    private var calls: [String] { KeptExportURLProtocol.seen.map { "\($0.method) \($0.path)" } }

    private static func exportJSON(id: String, folder: String, format: String, per: String) -> String {
        #"{"id":"\#(id)","folder":"\#(folder)","format":"\#(format)","per":"\#(per)","files":[],"#
            + #""in_the_way":[],"pending":0,"last_written":null}"#
    }

    // MARK: Adding

    /// WHY: a row on the screen is a promise that the folder will be kept current. Continue must
    /// send each row's folder, format and per exactly as chosen (a plain-text per-document export
    /// that arrived as Word per page would hand the person the wrong files), the kept export must
    /// join the list, and a row with no folder chosen is not an export and sends nothing.
    @Test("Continue keeps each row: POST /api/export/kept with its folder, format and per")
    func addingAKeptExportPostsFolderFormatPer() async throws {
        let client = makeClient { request in
            switch (request.httpMethod ?? "GET", request.url?.path ?? "") {
            case ("POST", "/api/export/kept"):
                let body = KeptExportURLProtocol.seen.last?.body ?? [:]
                return (200, Self.exportJSON(id: "k1", folder: body["folder"] as? String ?? "",
                                             format: body["format"] as? String ?? "", per: body["per"] as? String ?? ""))
            default:
                return (404, "{}")
            }
        }
        let store = KeptExportStore(client: client)
        store.addDraft()
        store.drafts[0].folder = URL(fileURLWithPath: "/Users/historian/Exports/Text")
        store.drafts[0].format = .plainText
        store.drafts[0].per = .document
        store.addDraft()   // no folder chosen: not an export

        #expect(await store.keepDrafts())

        let posts = KeptExportURLProtocol.seen.filter { $0.method == "POST" }
        #expect(posts.count == 1, "only the row with a folder is kept")
        let post = try #require(posts.first)
        #expect(post.path == "/api/export/kept")
        #expect(post.body["folder"] as? String == "/Users/historian/Exports/Text")
        #expect(post.body["format"] as? String == "plain-text")
        #expect(post.body["per"] as? String == "document")
        #expect(store.exports.map(\.id) == ["k1"])
        #expect(store.drafts.isEmpty, "a kept row leaves the rows to keep")
    }

    /// WHY: a refused row (a folder inside the project, a system folder) must stay on the screen
    /// with the engine's own sentence, so the person can choose another folder; Continue must not
    /// move on as if it were kept.
    @Test("a refused row stays, with the engine's sentence")
    func refusedRowStaysWithEngineWords() async {
        let client = makeClient { _ in
            (422, #"{"detail":"That folder is inside the project; choose one outside it."}"#)
        }
        let store = KeptExportStore(client: client)
        store.drafts = [.init(folder: URL(fileURLWithPath: "/tmp/test.fichero/out"), format: .word, per: .document)]

        #expect(await store.keepDrafts() == false)
        #expect(store.drafts.count == 1)
        #expect(store.errorMessage == "That folder is inside the project; choose one outside it.")
        #expect(store.exports.isEmpty)
    }

    // MARK: Page formats are per page

    /// WHY: ALTO, PAGE XML, TEI and hOCR each describe one page; the engine refuses them per
    /// document. The row must not be able to hold that combination (choosing a page format makes
    /// it per page, and per document cannot be chosen for one), and a request must never ask for it.
    @Test("page formats cannot be per document")
    func pageFormatsCannotBePerDocument() async throws {
        for format in [KeptExportStore.Format.alto, .pagexml, .tei, .hocr] {
            #expect(!KeptExportStore.allowsPerDocument(format), "\(format.rawValue) is per page only")
            var draft = KeptExportStore.Draft(folder: nil, format: .word, per: .document)
            draft.format = format
            #expect(draft.per == .page, "choosing \(format.rawValue) makes the row per page")
            draft.per = .document
            #expect(draft.per == .page, "per document cannot be chosen for \(format.rawValue)")
        }
        for format in [KeptExportStore.Format.word, .markdown, .plainText] {
            #expect(KeptExportStore.allowsPerDocument(format))
        }
        #expect(KeptExportStore.formats.count == 7, "Word, Markdown, plain text, ALTO, PAGE, TEI, hOCR")

        let client = makeClient { request in
            let body = KeptExportURLProtocol.seen.last?.body ?? [:]
            return (200, Self.exportJSON(id: "k2", folder: "/Exports/ALTO", format: body["format"] as? String ?? "",
                                         per: body["per"] as? String ?? ""))
        }
        let store = KeptExportStore(client: client)
        #expect(await store.keep(folder: URL(fileURLWithPath: "/Exports/ALTO"), format: .alto, per: .document))
        #expect(KeptExportURLProtocol.seen.last?.body["per"] as? String == "page", "never asked per document")
    }

    // MARK: Removing, writing

    /// WHY: × on a kept export must DELETE that export's own route (the engine stops writing; the
    /// files stay), and only that row leaves the list.
    @Test("removing a kept export calls DELETE and removes only that row")
    func removingCallsDelete() async {
        let client = makeClient { request in
            switch (request.httpMethod ?? "GET", request.url?.path ?? "") {
            case ("GET", "/api/export/kept"):
                return (200, #"{"exports":[\#(Self.exportJSON(id: "k1", folder: "/Exports/Word", format: "word", per: "document")),"#
                        + #"\#(Self.exportJSON(id: "k2", folder: "/Exports/ALTO", format: "alto", per: "page"))]}"#)
            case ("DELETE", "/api/export/kept/k1"):
                return (200, #"{"id":"k1"}"#)
            default:
                return (404, "{}")
            }
        }
        let store = KeptExportStore(client: client)
        await store.load()
        #expect(store.exports.map(\.id) == ["k1", "k2"])

        #expect(await store.remove("k1"))
        #expect(calls.last == "DELETE /api/export/kept/k1")
        #expect(store.exports.map(\.id) == ["k2"])
    }

    /// WHY: Write Now in the Inspector must ask the engine to write that export (its job goes to
    /// Activity), and the row must say it is writing.
    @Test("Write Now posts the export's write route")
    func writeNowPostsWrite() async {
        let client = makeClient { request in
            request.url?.path == "/api/export/kept/k1/write" ? (200, #"{"id":"k1","job_id":"j1"}"#) : (404, "{}")
        }
        let store = KeptExportStore(client: client)

        #expect(await store.writeNow("k1"))
        #expect(calls == ["POST /api/export/kept/k1/write"])
        #expect(store.writing.contains("k1"))
    }
}
