import Foundation
import Testing
@testable import fichero

@Suite struct NoteStaleResolutionTests {
    let now = Date(timeIntervalSince1970: 1_700_000_000)

    @Test func keepMineSavesAgainstTheCurrentVersion() {
        #expect(NoteStaleResolution.decide(keepMine: true, currentUpdatedAt: now) == .saveAgainst(now))
    }

    @Test func aNoteDeletedOnTheOtherMacStaysDeleted() {
        // WHY: shared editing: the other Mac's delete wins; no resurrection, no keep-mine offer.
        #expect(NoteStaleResolution.decide(keepMine: true, currentUpdatedAt: nil) == .deletedElsewhere)
    }

    @Test func takeTheirsCopiesTheDroppedText() {
        #expect(NoteStaleResolution.decide(keepMine: false, currentUpdatedAt: now) == .copyAndTakeTheirs)
        #expect(NoteStaleResolution.decide(keepMine: false, currentUpdatedAt: nil) == .copyAndTakeTheirs)
    }

    @Test func compareShowsBothTexts() {
        let c = NoteStaleResolution.comparison(mine: "my text", theirs: "their text")
        #expect(c == NoteStaleComparison(mine: "my text", theirs: "their text"))
    }

    @Test func compareHasNothingToShowWhenTheNoteWasDeletedElsewhere() {
        #expect(NoteStaleResolution.comparison(mine: "my text", theirs: nil) == nil)
    }
}
