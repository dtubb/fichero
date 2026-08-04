@testable import Fichero
import XCTest

final class EntityReconciliationCandidateTests: XCTestCase {
    func testIdUsesOrderedEntityPair() {
        let candidate = EntityReconciliationCandidate(
            entityAId: "a",
            entityAName: "Alpha",
            entityBId: "b",
            entityBName: "Beta",
            jaccard: 0.5,
            entityType: "person"
        )

        XCTAssertEqual(candidate.id, "a|b")
    }
}
