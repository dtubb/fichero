@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// Correct This Line (#5499, `source.reading.correct-a-line`): the app sends the line and its words to the
/// engine's one verb, `POST /api/segments/{id}/correct`, with the reading the person saw as the stale check,
/// and nothing else. Through the real `SegmentService` over the generated client; only the transport is stubbed.
@MainActor
@Suite(.serialized)
struct CorrectThisLineTests {
    private final class CorrectRoute: URLProtocol {
        nonisolated(unsafe) static var status = 200
        nonisolated(unsafe) static var seen: [(path: String, body: [String: Any])] = []

        override static func canInit(with request: URLRequest) -> Bool {
            request.url?.host == "correct.test" && request.url?.path.hasPrefix("/api/segments") == true
        }
        override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            let body = (try? JSONSerialization.jsonObject(with: request.bodyOrStream())) as? [String: Any] ?? [:]
            Self.seen.append((request.url?.path ?? "", body))
            let json = #"{"id":"rep-2","document_id":"p1","kind":"transcription","content":"y por el precio","#
                + #""source_anchor":{"document_id":"p1"}}"#
            let response = HTTPURLResponse(url: request.url!, statusCode: Self.status, httpVersion: nil,
                                           headerFields: ["Content-Type": "application/json"])!
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Data(Self.status == 200 ? json.utf8 : #"{"detail":"stale"}"#.utf8))
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private func service(status: Int) -> SegmentService {
        CorrectRoute.status = status
        CorrectRoute.seen = []
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CorrectRoute.self]
        return SegmentService(ficheroClient: FicheroClient(
            baseURL: URL(string: "https://correct.test")!, libraryPath: "/tmp/correct.fichero",
            session: URLSession(configuration: configuration)
        ))
    }

    /// WHY: a correction must be the engine's one verb -- the line and its words -- so the app never works out
    /// which reading it corrects (that is the engine's, and it differs for a provisional reading).
    @Test("the line and its words go to the engine's correct route, with the reading the person saw")
    func sendsTheLineAndItsWords() async throws {
        let made = try await service(status: 200)
            .correctLine(segmentId: "l6", text: "y por el precio", expectedCountingId: "rep-1")
        #expect(made == "rep-2")
        let sent = try #require(CorrectRoute.seen.first)
        #expect(sent.path == "/api/segments/l6/correct")
        #expect(sent.body["text"] as? String == "y por el precio")
        #expect(sent.body["expected_counting_id"] as? String == "rep-1")
        #expect(Set(sent.body.keys).isSubset(of: ["text", "expected_counting_id", "kind"]), "nothing else is sent")
    }

    /// WHY: when another reading counts now the engine refuses and nothing is written; the person is told.
    @Test("a stale correction is refused with words, not swallowed")
    func staleIsSaid() async {
        await #expect(throws: SegmentServiceError.self) {
            _ = try await service(status: 409).correctLine(segmentId: "l6", text: "y por", expectedCountingId: "old")
        }
    }

    @Test("the verb is offered on a line, and sends only words that change it")
    func offeredOnALineWithChangedWords() {
        #expect(CorrectLine.text("  y por el precio ", replacing: "y por el precio") == nil, "unchanged is no correction")
        #expect(CorrectLine.text("   ", replacing: "y por") == nil)
        #expect(CorrectLine.text(" y por el precio", replacing: "y por el preçio") == "y por el precio")
        #expect(CorrectLine.text("enel", replacing: nil) == "enel", "an unread line takes its first words")
        #expect(!CorrectLine.offers(nil))
    }
}
