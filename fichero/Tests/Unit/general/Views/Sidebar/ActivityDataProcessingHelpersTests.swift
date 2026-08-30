@testable import Fichero
import Foundation
import XCTest

/// Tests for pure ActivityDataProcessing helpers (#1993 Views). These string
/// transforms shape what the Activity UI shows; the edge cases (hash-prefix
/// detection, hidden plumbing node ids) are where they go wrong.
final class ActivityDataProcessingHelpersTests: XCTestCase {

    // MARK: - ActivityWorkflowGroup.key

    func testGroupKeyPrefersWorkflowIdElseNameFallback() {
        XCTAssertEqual(ActivityWorkflowGroup.key(workflowId: "wf-1", workflowName: "X"), "wf-1")
        XCTAssertEqual(
            ActivityWorkflowGroup.key(workflowId: nil, workflowName: "My WF"),
            "name:My WF"
        )
    }

    // MARK: - activityCleanWorkflowName

    func testCleanWorkflowNameStripsPrefixOnlyWhenPresent() {
        XCTAssertEqual(activityCleanWorkflowName("Workflow Catalogue"), "Catalogue")
        XCTAssertEqual(activityCleanWorkflowName("Catalogue"), "Catalogue")
        XCTAssertEqual(activityCleanWorkflowName("Workflow "), "")
        // Case-sensitive: a lowercase prefix is not stripped.
        XCTAssertEqual(activityCleanWorkflowName("workflow x"), "workflow x")
    }

    // MARK: - activityCleanFilename

    func testCleanFilenameStripsHexHashPrefix() {
        XCTAssertEqual(activityCleanFilename("a1b2c3_report.pdf"), "report.pdf")
        XCTAssertEqual(activityCleanFilename("deadbeef12_scan.png"), "scan.png")
        // Only the first underscore splits, so the rest of the name is preserved.
        XCTAssertEqual(activityCleanFilename("a1b2c3_my_file.png"), "my_file.png")
    }

    func testCleanFilenameLeavesNonHashNamesAlone() {
        XCTAssertEqual(activityCleanFilename("report.pdf"), "report.pdf")          // no underscore
        XCTAssertEqual(activityCleanFilename("nothex9_x.png"), "nothex9_x.png")    // not all hex
        XCTAssertEqual(activityCleanFilename("abc_x.png"), "abc_x.png")            // prefix too short (<6)
        XCTAssertEqual(activityCleanFilename("abcdef0123456_x.png"), "abcdef0123456_x.png")  // too long (>12)
    }

    // MARK: - activityHumanNodeName

    func testHumanNodeNameHidesPlumbing() {
        XCTAssertNil(activityHumanNodeName("12345678-1234-1234-1234-123456789012"))  // UUID slot
        XCTAssertNil(activityHumanNodeName("__start__"))                              // dunder
        XCTAssertNil(activityHumanNodeName("__pregel_pull"))
        XCTAssertNil(activityHumanNodeName("fan_out"))                                // hidden internal
    }

    func testHumanNodeNameTitleCasesRealNodes() {
        XCTAssertEqual(activityHumanNodeName("extract_entities"), "Extract Entities")
        XCTAssertEqual(activityHumanNodeName("transcribe"), "Transcribe")
    }
}
