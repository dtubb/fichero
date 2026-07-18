@testable import Fichero
import XCTest

final class SSEEventDataTests: XCTestCase {
    func testDecodesOptionalParallelFieldsAndData() throws {
        let event = try JSONDecoder().decode(
            SSEEventData.self,
            from: Data(#"{"event":"file_start","thread_id":"t-1","workflow_id":"wf-1","data":{"count":3},"timestamp":"2026-07-18T00:00:00Z","node_id":"n-1","file_path":"/tmp/a.pdf","file_index":1,"file_total":4,"progress":0.25,"document_id":"d-1","page_id":"p-1","display_name":"Page 1","sequence":2}"#.utf8)
        )

        XCTAssertEqual(event.event, "file_start")
        XCTAssertEqual(event.threadId, "t-1")
        XCTAssertEqual(event.nodeId, "n-1")
        XCTAssertEqual(event.fileIndex, 1)
        XCTAssertEqual(event.progress, 0.25)
        XCTAssertEqual(event.data["count"]?.intValue, 3)
    }
}
