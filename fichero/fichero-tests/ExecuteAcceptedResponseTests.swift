@testable import Fichero
import XCTest

final class ExecuteAcceptedResponseTests: XCTestCase {
    func testDecodesAcceptedResponseWireKeys() throws {
        let response = try JSONDecoder().decode(
            ExecuteAcceptedResponse.self,
            from: Data(#"{"thread_id":"t-1","workflow_id":"wf-1","workflow_name":"Import","status":"accepted","stream_url":"/stream/t-1"}"#.utf8)
        )

        XCTAssertEqual(response.threadId, "t-1")
        XCTAssertEqual(response.workflowId, "wf-1")
        XCTAssertEqual(response.workflowName, "Import")
        XCTAssertEqual(response.status, "accepted")
        XCTAssertEqual(response.streamUrl, "/stream/t-1")
    }
}
