@testable import FicheroAPIClient
import Foundation
import HTTPTypes
import OpenAPIRuntime
import XCTest

/// #6446: the tagged pollers send `If-None-Match` and a 304 comes back to the caller as the held 200.
final class ConditionalGetMiddlewareTests: XCTestCase {
    private let base = URL(string: "https://127.0.0.1:8765")!

    private func stats() -> HTTPRequest {
        var request = HTTPRequest(method: .get, scheme: nil, authority: nil, path: "/api/stats")
        request.headerFields[HTTPField.Name("X-Fichero-Library-Path")!] = "/lib/a"
        return request
    }

    func testASecondReadSendsTheTagAndAnUnchangedAnswerComesBackAsTheHeldBody() async throws {
        let middleware = ConditionalGetMiddleware()
        var sent: [String?] = []
        let first = try await middleware.intercept(stats(), body: nil, baseURL: base, operationID: "stats") { request, _, _ in
            sent.append(request.headerFields[.ifNoneMatch])
            return (HTTPResponse(status: .ok, headerFields: [.eTag: "W/\"1\""]), HTTPBody("{\"a\":1}"))
        }
        XCTAssertEqual(first.0.status, .ok)
        let second = try await middleware.intercept(stats(), body: nil, baseURL: base, operationID: "stats") { request, _, _ in
            sent.append(request.headerFields[.ifNoneMatch])
            return (HTTPResponse(status: .notModified), nil)
        }
        XCTAssertEqual(sent, [nil, "W/\"1\""])
        XCTAssertEqual(second.0.status, .ok, "the caller never sees a 304")
        let data = try await Data(collecting: try XCTUnwrap(second.1), upTo: 1024)
        XCTAssertEqual(String(bytes: data, encoding: .utf8), "{\"a\":1}")
    }

    func testAnotherLibraryDoesNotShareTheHeldAnswerAndUntaggedPathsAreLeftAlone() async throws {
        let middleware = ConditionalGetMiddleware()
        _ = try await middleware.intercept(stats(), body: nil, baseURL: base, operationID: "stats") { _, _, _ in
            (HTTPResponse(status: .ok, headerFields: [.eTag: "W/\"1\""]), HTTPBody("x"))
        }
        var other = stats()
        other.headerFields[HTTPField.Name("X-Fichero-Library-Path")!] = "/lib/b"
        var tag: String?
        _ = try await middleware.intercept(other, body: nil, baseURL: base, operationID: "stats") { request, _, _ in
            tag = request.headerFields[.ifNoneMatch]
            return (HTTPResponse(status: .ok), nil)
        }
        XCTAssertNil(tag)
        XCTAssertFalse(ConditionalGetMiddleware.isTagged("/api/activity/jobs"))
        XCTAssertTrue(ConditionalGetMiddleware.isTagged("/api/stats?x=1"))
    }
}
