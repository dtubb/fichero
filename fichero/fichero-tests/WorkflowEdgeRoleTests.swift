@testable import Fichero
import XCTest

final class WorkflowEdgeRoleTests: XCTestCase {

    func testFilesToTranscribeRendersAsFanOut() {
        XCTAssertEqual(
            EdgeFanRoleResolver.role(sourceTool: "files", targetTool: "transcribe"),
            .fanOut
        )
    }

    func testCatalogueExtractorsRenderAsFanOutTargets() {
        for tool in ["extract_entities", "key_people", "timeline", "keywords"] {
            XCTAssertEqual(
                EdgeFanRoleResolver.role(sourceTool: "files", targetTool: tool),
                .fanOut,
                "\(tool) should show map/fan-out topology from file sources"
            )
        }
    }

    func testAggregateRendersAsFanInBeforeSourceFanOut() {
        XCTAssertEqual(
            EdgeFanRoleResolver.role(sourceTool: "transcribe", targetTool: "aggregate"),
            .fanIn
        )
    }
}
