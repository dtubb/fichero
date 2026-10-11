@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

private final class IIIFMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var seen: [(key: String, body: [String: Any])] = []
    override static func canInit(with request: URLRequest) -> Bool {
        (request.url?.path ?? "").hasPrefix("/api/iiif/")
    }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let key = "\(request.httpMethod ?? "GET") \(request.url?.path ?? "")"
        let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
        Self.seen.append((key, body))
        let json = #"{"job_id": "job-iiif-1", "url": "\#(body["url"] as? String ?? "https://example.org/m.json")"}"#
        let response = HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

/// Import from IIIF (#5671, the app half): an https manifest or collection into a folder, as a job in Activity; a
/// bound folder's source and Refresh in its Inspector.
@MainActor
@Suite(.serialized)
struct IIIFImportStoreTests {
    private func store() -> IIIFImportStore {
        IIIFMockURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [IIIFMockURLProtocol.self]
        return IIIFImportStore(client: FicheroClient(baseURL: URL(string: "https://test.fichero")!,
                                                     libraryPath: "/tmp/test.fichero",
                                                     session: URLSession(configuration: configuration)))
    }

    @Test("only an https address is taken as a source")
    func httpsOnly() {
        #expect(IIIFImportStore.source(from: " https://iiif.archivelab.org/iiif/x/manifest.json ") != nil)
        #expect(IIIFImportStore.source(from: "http://example.org/manifest.json") == nil)
        #expect(IIIFImportStore.source(from: "manifest.json") == nil)
        #expect(IIIFImportStore.source(from: "file:///Users/ana/manifest.json") == nil)
    }

    @Test("Import posts the source and the folder chosen, and keeps the job for Activity")
    func importStartsTheJob() async throws {
        let store = store()
        let url = try #require(IIIFImportStore.source(from: "https://example.org/iiif/collection.json"))
        #expect(await store.importSource(url, into: "letters"))
        let post = try #require(IIIFMockURLProtocol.seen.first { $0.key == "POST /api/iiif/import" })
        #expect(post.body["url"] as? String == "https://example.org/iiif/collection.json")
        #expect(post.body["folder_id"] as? String == "letters")
        #expect(store.startedJobId == "job-iiif-1")
        // A new folder named after the source: no folder sent.
        #expect(await store.importSource(url, into: nil))
        #expect(IIIFMockURLProtocol.seen.last?.body["folder_id"] == nil)
    }

    @Test("Refresh reads the bound folder's source again as one job")
    func refreshStartsTheJob() async {
        let store = store()
        #expect(await store.refresh(folderId: "letters"))
        #expect(IIIFMockURLProtocol.seen.map(\.key) == ["POST /api/iiif/folders/letters/refresh"])
        #expect(store.startedJobId == "job-iiif-1")
    }

    @Test("a folder bound to a source says where from and how many; any other says nothing")
    func boundFolderSaysItsSource() throws {
        let bound = Document(id: "letters", docType: .folder, name: "Letters", metadata: [
            "iiif_source": AnyCodable("https://example.org/iiif/collection.json"),
            "iiif_canvases": AnyCodable(1204), "iiif_withdrawn": AnyCodable(3)
        ])
        let source = try #require(IIIFFolderSource.of(bound))
        #expect(source.url == "https://example.org/iiif/collection.json")
        #expect(source.countsSentence == "\(1204.formatted()) pages; 3 no longer listed by the source, kept here")
        #expect(IIIFFolderSource.of(Document(id: "plain", docType: .folder, name: "Plain")) == nil)
    }
}
