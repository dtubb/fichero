@testable import Fichero
import Foundation
import XCTest

final class ClaimSummaryCardTests: XCTestCase {

    func testOpenClaimSourceUserInfoIncludesProvenanceFields() {
        let info = ClaimSummaryCard.openClaimSourceUserInfo(
            documentId: "doc-9",
            pageLabel: " 12 ",
            charStart: 101,
            charEnd: 127,
            claimId: "claim-42",
            excerpt: " Paris is the capital of France. "
        )

        XCTAssertEqual(info?["documentId"] as? String, "doc-9")
        XCTAssertEqual(info?["pageLabel"] as? String, "12")
        let charStart = (info?["charStart"] as? Int) ?? (info?["charStart"] as? NSNumber)?.intValue
        let charEnd = (info?["charEnd"] as? Int) ?? (info?["charEnd"] as? NSNumber)?.intValue
        XCTAssertEqual(charStart, 101)
        XCTAssertEqual(charEnd, 127)
        XCTAssertEqual(info?["claimId"] as? String, "claim-42")
        XCTAssertEqual(info?["excerpt"] as? String, "Paris is the capital of France.")
    }

    func testOpenClaimSourceUserInfoRejectsEmptyDocumentId() {
        let info = ClaimSummaryCard.openClaimSourceUserInfo(
            documentId: "",
            pageLabel: "12",
            charStart: 101,
            charEnd: 127,
            claimId: "claim-42",
            excerpt: "Paris is the capital of France."
        )

        XCTAssertNil(info)
    }
}
