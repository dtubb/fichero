//
//  StatementCorrectionTests.swift
//  FicheroTests
//
//  Correcting what is said about a line from the Inspector (#5602, `source.extract.corrected-in-place`):
//  a name re-pointed to another entity or its words fixed, a statement dated or rejected -- each sent
//  through the generated client to the engine's audited route, then the line's statements re-read with
//  each mark's spans and its "corrected by you" flag. Driven against a stub scoped to this suite's own
//  host, recording what each path was sent.
//

@testable import Fichero
import FicheroAPIClient
import XCTest

private final class StatementsMockURLProtocol: URLProtocol {
    private static let lock = NSLock()
    nonisolated(unsafe) static var handler: ((URLRequest) -> (Int, String))?
    nonisolated(unsafe) private static var log: [(path: String, method: String, body: [String: Any])] = []

    static func reset(_ handler: @escaping (URLRequest) -> (Int, String)) {
        lock.lock()
        self.handler = handler
        log = []
        lock.unlock()
    }

    /// Each request sent to `path`: its method and its JSON body.
    static func requests(to path: String) -> [(method: String, body: [String: Any])] {
        lock.lock()
        defer { lock.unlock() }
        return log.filter { $0.path == path }.map { ($0.method, $0.body) }
    }

    // swiftlint:disable:next static_over_final_class
    override class func canInit(with request: URLRequest) -> Bool {
        request.url?.host == "statements.test"
    }

    // swiftlint:disable:next static_over_final_class
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    nonisolated private static func bodyData(_ request: URLRequest) -> Data {
        if let body = request.httpBody { return body }
        guard let stream = request.httpBodyStream else { return Data() }
        stream.open()
        defer { stream.close() }
        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let read = stream.read(&buffer, maxLength: buffer.count)
            guard read > 0 else { break }
            data.append(buffer, count: read)
        }
        return data
    }

    override func startLoading() {
        guard let url = request.url else { return }
        let body = (try? JSONSerialization.jsonObject(with: Self.bodyData(request))) as? [String: Any] ?? [:]
        Self.lock.lock()
        Self.log.append((url.path, request.httpMethod ?? "", body))
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

/// What `mentions/repoint` and `mentions/respan` answer: where the corrected mention now sits.
nonisolated private let correctedOK = #"""
{"entity_id":"e-pedro","document_id":"doc-1","source_char_start":112,"source_char_end":116,
 "excerpt":"Juan","segment_id":"seg-1","audit_id":"a-1"}
"""#

@MainActor
final class StatementCorrectionTests: XCTestCase {
    private func makeService() -> StatementService {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StatementsMockURLProtocol.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://statements.test")!,
            libraryPath: "/tmp/statements.fichero",
            session: URLSession(configuration: configuration)
        )
        return StatementService(client: client)
    }

    override func tearDown() {
        StatementsMockURLProtocol.handler = nil
        super.tearDown()
    }

    /// The mark "Juan" at 112..116 of the page text, 12..16 on its line.
    private let juan = InspectorStatements.Mention(
        id: "e-juan", name: "Juan de Mosquera", entityType: "person", excerpt: "Juan",
        sourceCharStart: 112, sourceCharEnd: 116, charStart: 12, charEnd: 16
    )

    /// WHY: the line's read is what the section re-reads after a correction; without each mark's page
    /// span nothing can be sent about it, and without the person flag the "corrected by you" badge lies.
    func testTheLinesReadCarriesEachMarksSpansAndWhoPlacedIt() async throws {
        StatementsMockURLProtocol.reset { _ in
            (200, #"""
            {"segment_id":"seg-1","claims":[{"claim_id":"c-1","text":"Juan sold the mine","curation_state":"unreviewed",
              "confidence":0.6,"via":"anchor","excerpt":"Juan vendió","char_start":12,"char_end":23}],
             "mentions":[{"entity_id":"e-juan","name":"Juan de Mosquera","entity_type":"person","excerpt":"Juan",
              "source_char_start":112,"source_char_end":116,"char_start":12,"char_end":16,"corrected_by_person":true},
              {"entity_id":"e-istmina","name":"Istmina","entity_type":"place","excerpt":null}]}
            """#)
        }
        let answer = try await makeService().statements(segmentId: "seg-1")
        XCTAssertEqual(answer.mentions.first, InspectorStatements.Mention(
            id: "e-juan", name: "Juan de Mosquera", entityType: "person", excerpt: "Juan",
            sourceCharStart: 112, sourceCharEnd: 116, charStart: 12, charEnd: 16, correctedByPerson: true
        ))
        XCTAssertEqual(answer.mentions.last?.correctedByPerson, false, "an absent flag is a machine's mark")
        XCTAssertNil(answer.mentions.last?.pageSpan, "a mark with no page span cannot be corrected")
        let rows = InspectorStatements.rows(answer)
        XCTAssertEqual(rows.map(\.corrected), [false, true, false])
    }

    /// WHY: "Not this person… (choose another)" is one audited `mention.repoint`, naming the mark by its
    /// page-text span on the entity it leaves.
    func testNotThisPersonRepointsTheMarkToTheChosenEntity() async throws {
        StatementsMockURLProtocol.reset { _ in (200, correctedOK) }
        try await makeService().repoint(juan, documentId: "doc-1", toEntityId: "e-pedro")

        let sent = StatementsMockURLProtocol.requests(to: "/api/entities/e-juan/mentions/repoint")
        XCTAssertEqual(sent.map(\.method), ["POST"])
        XCTAssertEqual(sent.first?.body["document_id"] as? String, "doc-1")
        XCTAssertEqual(sent.first?.body["char_start"] as? Int, 112)
        XCTAssertEqual(sent.first?.body["char_end"] as? Int, 116)
        XCTAssertEqual(sent.first?.body["to_entity_id"] as? String, "e-pedro")
    }

    /// WHY: "Fix the words" sends the old span and the new one, both in the page text, as `mention.respan`.
    func testFixTheWordsRespansTheMarkInThePageText() async throws {
        StatementsMockURLProtocol.reset { _ in (200, correctedOK) }
        try await makeService().respan(juan, documentId: "doc-1", newStart: 112, newEnd: 128)

        let sent = StatementsMockURLProtocol.requests(to: "/api/entities/e-juan/mentions/respan")
        XCTAssertEqual(sent.map(\.method), ["POST"])
        let body = try XCTUnwrap(sent.first?.body)
        XCTAssertEqual(body["char_start"] as? Int, 112)
        XCTAssertEqual(body["char_end"] as? Int, 116)
        XCTAssertEqual(body["new_char_start"] as? Int, 112)
        XCTAssertEqual(body["new_char_end"] as? Int, 128)
    }

    /// WHY: a statement's date and its rejection go through the claim's one action each (`claim.patch`,
    /// `claim.transition`); the rejection is a person's (`to_state`, not the old hand-rolled `state`).
    func testChangeDateAndNotTrueGoThroughTheClaimRoutes() async throws {
        StatementsMockURLProtocol.reset { request in
            switch request.url?.path {
            case "/api/claims/c-1":
                return (200, #"{"id":"c-1","text":"Juan sold the mine","time_start":"1650-03-01"}"#)
            case "/api/claims/c-1/transition":
                return (200, #"""
                {"claim_id":"c-1","success":true,"from_state":"unreviewed","to_state":"rejected",
                 "transitioned_at":"2026-10-08T12:00:00Z"}
                """#)
            default:
                return (404, "{}")
            }
        }
        let service = makeService()
        try await service.setDate(claimId: "c-1", date: "1650-03-01")
        try await service.reject(claimId: "c-1")

        let dated = StatementsMockURLProtocol.requests(to: "/api/claims/c-1")
        XCTAssertEqual(dated.map(\.method), ["PATCH"])
        XCTAssertEqual(dated.first?.body["time_start"] as? String, "1650-03-01")
        XCTAssertEqual(dated.first?.body.count, 1, "only the date is sent; every other field stays")
        let rejected = StatementsMockURLProtocol.requests(to: "/api/claims/c-1/transition")
        XCTAssertEqual(rejected.map(\.method), ["PATCH"])
        XCTAssertEqual(rejected.first?.body["to_state"] as? String, "rejected")
        XCTAssertEqual(rejected.first?.body["reviewed_by"] as? String, "human")
        // #5613: the deleted hand-rolled path sent `state`, which the engine refuses (422).
        XCTAssertNil(rejected.first?.body["state"], "the old hand-rolled `state` key is never sent")
    }

    /// WHY: a refused correction is thrown, not swallowed, so the section can say it -- and a mark with
    /// no page span is refused before anything is sent.
    func testARefusalIsThrownAndASpanlessMarkSendsNothing() async throws {
        StatementsMockURLProtocol.reset { _ in (422, #"{"detail":[{"loc":["body"],"msg":"no mention there","type":"value_error"}]}"#) }
        let service = makeService()
        do {
            try await service.repoint(juan, documentId: "doc-1", toEntityId: "e-pedro")
            XCTFail("a refused re-point throws")
        } catch {
            XCTAssertNotNil(error as? SegmentServiceError)
        }
        let spanless = InspectorStatements.Mention(id: "e-x", name: "X", entityType: "person")
        do {
            try await service.respan(spanless, documentId: "doc-1", newStart: 0, newEnd: 3)
            XCTFail("a mark with no page span is refused")
        } catch {
            XCTAssertTrue(StatementsMockURLProtocol.requests(to: "/api/entities/e-x/mentions/respan").isEmpty)
        }
    }
}
