//
//  ProposedKindTests.swift
//  FicheroTests
//
//  A run's proposed kind (#5600, `source.extract.kinds-proposed-as-prototypes`): the Inspector reads the
//  proposal the engine keeps on the node (`metadata.proposed_attributes.prototype`) and answers it through
//  the engine's two routes. Driven through the generated client against a stub scoped to this suite's own
//  host, recording what each path was sent.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

private final class KindsMockURLProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    nonisolated(unsafe) private static var log: [(path: String, method: String)] = []

    static func reset(_ handler: @escaping (URLRequest) -> (Int, String)) {
        lock.lock()
        self.handler = handler
        log = []
        lock.unlock()
    }

    static func requests(to path: String) -> [String] {
        lock.lock()
        defer { lock.unlock() }
        return log.filter { $0.path == path }.map(\.method)
    }

    // swiftlint:disable:next static_over_final_class
    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "kinds.test"
    }

    // swiftlint:disable:next static_over_final_class
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let url = request.url else { return }
        Self.lock.lock()
        Self.log.append((url.path, request.httpMethod ?? ""))
        let handler = Self.handler
        Self.lock.unlock()
        let (status, json) = handler?(request) ?? (404, "{}")
        guard let response = HTTPURLResponse(url: url, statusCode: status, httpVersion: "HTTP/1.1",
                                             headerFields: ["Content-Type": "application/json"]) else { return }
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }

    override func stopLoading() {}
}

@MainActor
final class ProposedKindTests: XCTestCase {
    /// A node's metadata as `GET /api/documents/{id}` sends it, with a proposal in `state`.
    private func metadata(state: String) throws -> [String: AnyCodable] {
        let json = """
        {"title":"A letter","proposed_attributes":{"prototype":{"value":"letter","label":"Letter",
         "state":"\(state)","proposed_at":"2026-10-08T10:00:00+00:00",
         "source":{"by":"machine","tool":"classify","step":null,"run_id":"1a2b3c4d5e6f7a8b",
                   "artifact_id":"art-1","provider":"omlx","model":"qwen2.5-vl-3b",
                   "said":"A letter: it opens with a salutation.","cites":null}}}}
        """
        return try JSONDecoder().decode([String: AnyCodable].self, from: Data(json.utf8))
    }

    private func makeService() -> EntityService {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [KindsMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://kinds.test")!,
            libraryPath: "/tmp/kinds.fichero",
            session: URLSession(configuration: configuration)
        )
        return EntityService(ficheroClient: client)
    }

    override func tearDown() {
        KindsMockURLProtocol.handler = nil
        super.tearDown()
    }

    /// WHY (`source.extract.kinds-proposed-as-prototypes`): the Inspector shows the kind the run named,
    /// what the model said and which run, exactly as the engine kept them; an answered proposal (or none)
    /// shows nothing to answer.
    func testAWaitingProposalIsReadAsTheEngineWroteIt() throws {
        let proposal = try XCTUnwrap(ProposedKind(metadata: try metadata(state: "proposed")))
        XCTAssertEqual(proposal.key, "letter")
        XCTAssertEqual(proposal.label, "Letter")
        XCTAssertEqual(proposal.said, "A letter: it opens with a salutation.")
        XCTAssertEqual(proposal.byWhom, "Proposed by classify (qwen2.5-vl-3b) in run 1a2b3c4d")
        XCTAssertNil(ProposedKind(metadata: try metadata(state: "accepted")))
        XCTAssertNil(ProposedKind(metadata: try metadata(state: "rejected")))
        XCTAssertNil(ProposedKind(metadata: [:]))
        XCTAssertNotNil(ProposedKind.preview)
    }

    /// WHY: Accept and Reject are the engine's audited answers, one POST each to the node's own route;
    /// a refusal is thrown, not swallowed, so the row can say it.
    func testAcceptAndRejectPostToTheNodesRoutes() async throws {
        KindsMockURLProtocol.reset { request in
            switch request.url?.path {
            case "/api/documents/doc-1/proposed-kind/accept":
                return (200, #"{"document_id":"doc-1","prototype_key":"letter","state":"accepted","audit_id":"a-1"}"#)
            case "/api/documents/doc-1/proposed-kind/reject":
                return (200, #"{"document_id":"doc-1","prototype_key":null,"state":"rejected","audit_id":"a-2"}"#)
            default:
                return (404, #"{"detail":"No proposed kind is waiting on doc-2"}"#)
            }
        }
        let service = makeService()

        let accepted = try await service.acceptProposedKind(documentId: "doc-1")
        XCTAssertEqual(accepted.prototypeKey, "letter")
        XCTAssertEqual(accepted.state, "accepted")
        let rejected = try await service.rejectProposedKind(documentId: "doc-1")
        XCTAssertEqual(rejected.state, "rejected")
        XCTAssertNil(rejected.prototypeKey)

        XCTAssertEqual(KindsMockURLProtocol.requests(to: "/api/documents/doc-1/proposed-kind/accept"), ["POST"])
        XCTAssertEqual(KindsMockURLProtocol.requests(to: "/api/documents/doc-1/proposed-kind/reject"), ["POST"])

        do {
            try await service.acceptProposedKind(documentId: "doc-2")
            XCTFail("a proposal no longer waiting is refused")
        } catch {
            XCTAssertNotNil(error as? EntityService.ServiceError)
        }
    }
}
