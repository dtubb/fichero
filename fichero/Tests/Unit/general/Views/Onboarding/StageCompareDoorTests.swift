@testable import Fichero
import Foundation
import Testing

/// `wide.compare.one-view-from-the-pager`, `wide.compare.replaces-the-captions-and-the-animation` (#6052): Compare at two models and
/// not at one; in the wide Set Up the counts' caption is gone and the comparison is the real result.
@MainActor
struct StageCompareDoorTests {
    private func result() throws -> SetupStageTryResult {
        let json = """
        {"state":"done","candidates":[
          {"card":"a","name":"A","runs_on":"this-mac","local":true,"per_page":[{"id":"p1","readings":[{"text":"x"}]}]},
          {"card":"b","name":"B","runs_on":"this-mac","local":true,"per_page":[{"id":"p1","readings":[{"text":"y"}]}]}]}
        """
        return try JSONDecoder().decode(SetupStageTryResult.self, from: Data(json.utf8))
    }

    @Test func compareIsOfferedAtTwoModelsAndNotAtOne() {
        #expect(!StageCompareDoor.showsCompare(candidates: 0))
        #expect(!StageCompareDoor.showsCompare(candidates: 1))
        #expect(StageCompareDoor.showsCompare(candidates: 2))
        #expect(StageCompareDoor.showsCompare(candidates: 3))
    }

    @Test func theCountsCaptionGoesInTheWideSetUpAndStaysOtherwise() {
        #expect(!StageCompareColumns.showsCountCaption(wide: true))
        #expect(StageCompareColumns.showsCountCaption(wide: false))
    }

    @Test func theComparisonIsOnTheFirstPageAModelRead() throws {
        let columns = StageCandidate.columns(try result().candidates)
        #expect(StageShowcaseSection.firstPage(of: columns) == "p1")
        #expect(StageShowcaseSection.firstPage(of: []) == nil)
    }
}
