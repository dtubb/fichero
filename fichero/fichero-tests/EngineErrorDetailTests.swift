import FicheroAPIClient
import XCTest

/// The engine's error message must reach the user (#3802).
///
/// The app used to flatten every 4xx/5xx to a generic string, so a workflow that
/// 400'd with `{"detail": "Workflow validation failed: X"}` showed only
/// "Server error (400): Execute workflow failed" — the reason discarded. These pin
/// the decode that fixes it, and the fallbacks that keep a malformed body from
/// crashing or misleading.
final class EngineErrorDetailTests: XCTestCase {

    private func data(_ json: String) -> Data { Data(json.utf8) }

    // MARK: - The case the user hit

    func testStringDetailIsSurfaced() {
        let body = data(#"{"detail": "Workflow validation failed: node 'x' has no input"}"#)
        XCTAssertEqual(
            EngineErrorDetail.message(from: body),
            "Workflow validation failed: node 'x' has no input"
        )
    }

    // MARK: - Fallbacks — a bad body must yield nil, never a crash or a lie

    func testEmptyBodyYieldsNil() {
        XCTAssertNil(EngineErrorDetail.message(from: Data()))
    }

    func testNilBodyYieldsNil() {
        XCTAssertNil(EngineErrorDetail.message(from: nil))
    }

    func testNonJSONBodyYieldsNil() {
        XCTAssertNil(EngineErrorDetail.message(from: data("<html>502 Bad Gateway</html>")))
    }

    func testJSONWithoutDetailKeyYieldsNil() {
        XCTAssertNil(EngineErrorDetail.message(from: data(#"{"error": "nope"}"#)))
    }

    func testWhitespaceOnlyDetailYieldsNil() {
        XCTAssertNil(EngineErrorDetail.message(from: data(#"{"detail": "   "}"#)))
    }

    // MARK: - FastAPI 422 validation errors (detail is an array, not a string)

    func testValidationDetailArrayIsReadable() {
        let body = data(#"""
        {"detail": [
          {"loc": ["body", "limit"], "msg": "must be positive", "type": "value_error"},
          {"loc": ["body", "name"], "msg": "field required", "type": "missing"}
        ]}
        """#)
        XCTAssertEqual(
            EngineErrorDetail.message(from: body),
            "limit: must be positive; name: field required"
        )
    }

    /// A `loc` mixes strings and array indices — decoding must not choke on the ints.
    func testValidationLocWithArrayIndexDecodes() {
        let body = data(#"{"detail": [{"loc": ["body", "items", 0, "id"], "msg": "bad"}]}"#)
        XCTAssertEqual(EngineErrorDetail.message(from: body), "items.0.id: bad")
    }

    func testValidationArrayWithNoUsableMessagesYieldsNil() {
        XCTAssertNil(EngineErrorDetail.message(from: data(#"{"detail": []}"#)))
    }
}
