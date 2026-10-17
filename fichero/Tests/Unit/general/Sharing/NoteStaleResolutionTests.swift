import Foundation
import Testing
@testable import fichero

@Suite struct NoteStaleResolutionTests {
    let now = Date(timeIntervalSince1970: 1_700_000_000)

    @Test func keepMineSavesAgainstTheCurrentVersion() {
        #expect(NoteStaleResolution.decide(keepMine: true, currentUpdatedAt: now) == .saveAgainst(now))
    }

    @Test func keepMineOfANoteDeletedOnTheOtherMacKeepsTheText() {
        // WHY: the other Mac deleted the note; dropping the person's text here is silent data loss.
        #expect(NoteStaleResolution.decide(keepMine: true, currentUpdatedAt: nil) == .copyBecauseDeleted)
    }

    @Test func takeTheirsCopiesTheDroppedText() {
        #expect(NoteStaleResolution.decide(keepMine: false, currentUpdatedAt: now) == .copyAndTakeTheirs)
        #expect(NoteStaleResolution.decide(keepMine: false, currentUpdatedAt: nil) == .copyAndTakeTheirs)
    }
}
