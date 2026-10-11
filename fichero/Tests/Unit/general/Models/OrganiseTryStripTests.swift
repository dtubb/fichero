@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Organise's page in Set Up draws its try (`finddocs.review.setup-page`, #5668), written from the spec and the
/// engine's answer: the samples are the stage's own run of consecutive pages (`GET /api/recipes/samples?stage=`),
/// the try's documents are dashed groups over the strip, and its entries sit under their pages.
private final class OrganiseSamplesURLProtocol: URLProtocol {
    nonisolated(unsafe) static var queries: [String] = []

    override static func canInit(with request: URLRequest) -> Bool { true }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url?.path ?? ""
        var body = #"{"detail":"not stubbed"}"#, status = 404
        if path == "/api/recipes/samples" {
            Self.queries.append(request.url?.query ?? "")
            status = 200
            body = #"{"chosen_by":"fichero","pages":[{"id":"a","name":"p1.jpg","why":"the run begins here"},"#
                + #"{"id":"b","name":"p2.jpg","why":"next in the folder"}]}"#
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
struct OrganiseTryStripTests {
    private static func document(_ name: String, _ pages: [String], _ confidence: Double? = 0.82) -> SetupStageProposedDocument {
        SetupStageProposedDocument(name: name, pageIds: pages, kind: "Sentencia", confidence: confidence, reasons: ["VISTOS"])
    }

    /// WHY: Organise cannot show where a document ends on scattered pages; the page asks for its stage's run.
    @Test("the samples are asked for the stage, so Organise gets its run of consecutive pages")
    func samplesAreTheStagesOwn() async {
        OrganiseSamplesURLProtocol.queries = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [OrganiseSamplesURLProtocol.self]
        let client = FicheroClient(baseURL: URL(string: "https://127.0.0.1:8765")!, libraryPath: "/tmp/Organise.fichero",
                                   session: URLSession(configuration: configuration))
        let store = SetupStageTryStore(client: client, stageId: "organise")
        await store.load()
        #expect(OrganiseSamplesURLProtocol.queries == ["stage=organise"])
        #expect(store.samples.map(\.id) == ["a", "b"])
    }

    @Test("the try's documents, entries and run are read from its result")
    func readsTheResult() throws {
        let json = """
        {"state":"done","pages":["a","b","c"],
         "documents":[{"page_ids":["a","b"],"name":"Sentencia","kind":"Sentencia","confidence":0.82,"reasons":["VISTOS"]}],
         "entries":[{"page_id":"c","name":"12 March 1924","opening":"Today the rain"}]}
        """
        let result = try JSONDecoder().decode(SetupStageTryResult.self, from: Data(json.utf8))
        #expect(result.pages == ["a", "b", "c"])
        #expect(result.documents?.first?.pageIds == ["a", "b"])
        #expect(result.entries == [SetupStageEntry(pageId: "c", name: "12 March 1924", opening: "Today the rain")])
    }

    /// WHY: a proposed document is drawn as one dashed group over its pages, in the run's order; a page in no
    /// document stands alone, so the person sees exactly where the run would cut.
    @Test("the strip groups each document's consecutive pages and leaves every other page on its own")
    func segments() {
        let sentencia = Self.document("Sentencia", ["b", "c"])
        let carta = Self.document("Carta", ["e"])
        let segments = OrganiseTryLayout.segments(pages: ["a", "b", "c", "d", "e"], documents: [sentencia, carta])
        #expect(segments == [.page("a"), .document(sentencia, pages: ["b", "c"]), .page("d"),
                             .document(carta, pages: ["e"])])
    }

    @Test("a document's page outside the run is not drawn, and two documents side by side stay two groups")
    func groupsStayApart() {
        let first = Self.document("Uno", ["a", "x"])
        let second = Self.document("Dos", ["b"])
        let segments = OrganiseTryLayout.segments(pages: ["a", "b"], documents: [first, second])
        #expect(segments == [.document(first, pages: ["a"]), .document(second, pages: ["b"])])
    }

    @Test("entries sit under the page they open on, in the engine's order; a group reads its name, kind and how sure")
    func entriesAndCaption() {
        let entries = [SetupStageEntry(pageId: "c", name: "12 March", opening: nil),
                       SetupStageEntry(pageId: "a", name: "1 March", opening: nil),
                       SetupStageEntry(pageId: "c", name: "13 March", opening: nil)]
        #expect(OrganiseTryLayout.entries(entries)["c"]?.map(\.name) == ["12 March", "13 March"])
        #expect(OrganiseTryLayout.entries(entries)["b"] == nil)
        #expect(OrganiseTryLayout.caption(Self.document("Sentencia", ["a"])) == "Sentencia · Sentencia · 82% sure")
        #expect(OrganiseTryLayout.caption(Self.document("Carta", ["a"], nil)) == "Carta · Sentencia")
    }
}
