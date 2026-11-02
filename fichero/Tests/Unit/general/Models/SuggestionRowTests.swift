@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// A stub scoped to the suggestions route, so it never races other suites' requests (#4024).
private final class SuggestionsMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var body = ""
    override static func canInit(with request: URLRequest) -> Bool { request.url?.path == "/api/recipes/suggestions" }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(Self.body.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

private let faded = """
{"id":"condition.faded","what":"Prepare Images: clarity",
 "why":"faded ink reads better after contrast (from 3 of 5 sample pages)",
 "from":"condition: faded","applied":false,"change":"about-the-material.condition"}
"""
private let kind = """
{"id":"defaults.model-kind","what":"Kraken reader","why":"nothing leaves this Mac",
 "from":"your answers on How","applied":true,"change":"how.model-kind"}
"""
private let leaveOut = """
{"id":"leave-out","what":"Leave out what is not writing before reading",
 "why":"4 of 5 sample pages have marks that are not writing",
 "from":"the sample's own findings","applied":false,"change":"stage.leave-out","price":"free"}
"""
private let listingJSON = "{\"items\":[\(faded),\(kind),\(leaveOut)]}"

/// The suggestion rows (`wide.suggest.reason-and-override`): the row's parts, the page each belongs to, the yours mark.
struct SuggestionRowTests {
    private func listing() throws -> [SuggestionRow] {
        try JSONDecoder().decode(Components.Schemas.SuggestionList.self, from: Data(listingJSON.utf8)).items
            .map { SuggestionRow(engine: $0) }
    }

    @Test("a row carries what, why, where it came from and where Change… goes")
    func threeParts() throws {
        let row = try #require(try listing().first)
        #expect(row.what == "Prepare Images: clarity")
        #expect(row.reasonLine == "faded ink reads better after contrast (from 3 of 5 sample pages) (condition: faded)")
        #expect(row.change == "about-the-material.condition" && row.applied == false && row.yours == false)
    }

    @Test("each page gets only its own rows")
    func pages() throws {
        let rows = try listing()
        #expect(rows.filter(SuggestionPage.aboutTheMaterial.includes).map(\.id) == ["condition.faded"])
        #expect(rows.filter(SuggestionPage.how.includes).map(\.id) == ["defaults.model-kind"])
        #expect(rows.filter(SuggestionPage.stage(jobs: ["leave-out", "prepare-the-image"]).includes).map(\.id) == ["leave-out"])
        #expect(rows.filter(SuggestionPage.ready.includes).isEmpty)
        #expect(rows.filter(SuggestionPage.stage(jobs: ["find-lines"]).includes).isEmpty)
    }

    @Test("a page name is a whole word of the change, not a prefix of another")
    func wholeWord() throws {
        let row = try #require(try listing().first)
        #expect(!row.isOn(page: "about"))
        #expect(row.isOn(page: "about-the-material"))
    }

    @MainActor
    @Test("a changed row reads yours, keeps its reason, and stays yours after the list is read again")
    func yours() async throws {
        SuggestionsMockURLProtocol.body = "{\"items\":[\(leaveOut)]}"
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [SuggestionsMockURLProtocol.self]
        let client = FicheroClient(baseURL: URL(string: "https://test.fichero")!, libraryPath: "/tmp/test.fichero",
                                   session: URLSession(configuration: configuration))
        let store = SuggestionsStore(client: client)
        await store.load()
        #expect(store.rows.map(\.yours) == [false])
        store.markChanged("leave-out")
        #expect(store.rows.first?.yours == true)
        #expect(store.rows.first?.why == "4 of 5 sample pages have marks that are not writing")
        await store.load()
        #expect(store.rows.first?.yours == true)
    }
}
