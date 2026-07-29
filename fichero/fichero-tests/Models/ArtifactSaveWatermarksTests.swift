@testable import Fichero
import XCTest

/// #4285 / #4286 — pasting into the content editor was silently lost when the
/// server rejected the save: the editor's watermarks were advanced BEFORE the
/// round-trip and never rolled back, so the draft read as clean, no retry
/// fired, and the next reseed replaced the buffer with stale stored content.
/// These tests pin the watermark transaction the editor now uses.
final class ArtifactSaveWatermarksTests: XCTestCase {

    // MARK: - Seeding

    func testSeedMakesStoredContentCleanAndSuppressesReseed() {
        var marks = ArtifactSaveWatermarks()
        marks.seed(raw: "stored", encoded: "stored-encoded")
        XCTAssertTrue(marks.isClean(encoded: "stored-encoded"))
        XCTAssertFalse(marks.shouldReseed(from: "stored"))
        XCTAssertTrue(marks.shouldReseed(from: "changed externally"))
    }

    func testPasteMakesDraftDirty() {
        var marks = ArtifactSaveWatermarks()
        marks.seed(raw: "", encoded: "")
        XCTAssertFalse(marks.isClean(encoded: "pasted artifact text"))
    }

    // MARK: - Successful save

    func testSuccessfulSaveLeavesDraftCleanAndSuppressesOwnEcho() {
        var marks = ArtifactSaveWatermarks()
        marks.seed(raw: "old", encoded: "old")
        _ = marks.beginSave(encoded: "pasted")
        // Save succeeded — no rollback. Draft is clean, and the engine echoing
        // the saved content back must NOT reseed (cursor reset, #2478).
        XCTAssertTrue(marks.isClean(encoded: "pasted"))
        XCTAssertFalse(marks.shouldReseed(from: "pasted"))
    }

    // MARK: - Failed save (the #4285 data-loss case)

    func testFailedSaveRollsBackToDirtySoRetryFires() {
        var marks = ArtifactSaveWatermarks()
        marks.seed(raw: "old", encoded: "old")
        let prior = marks.beginSave(encoded: "pasted")
        marks.rollBack(to: prior)
        // The paste must still read as DIRTY — a later auto-save / blur
        // flush / bounded retry re-attempts the identical content.
        XCTAssertFalse(marks.isClean(encoded: "pasted"))
    }

    func testFailedSaveDoesNotLetStaleStoredContentClobberTheDraft() {
        var marks = ArtifactSaveWatermarks()
        marks.seed(raw: "old", encoded: "old")
        let prior = marks.beginSave(encoded: "pasted")
        marks.rollBack(to: prior)
        // Stored content is unchanged (the save was rejected) — the reseed
        // guard must NOT fire, i.e. the dirty draft is preserved rather than
        // replaced with the stale "old" content.
        XCTAssertFalse(marks.shouldReseed(from: "old"))
    }

    func testFailedThenRetriedSaveEndsClean() {
        var marks = ArtifactSaveWatermarks()
        marks.seed(raw: "old", encoded: "old")
        // First attempt fails.
        let prior = marks.beginSave(encoded: "pasted")
        marks.rollBack(to: prior)
        XCTAssertFalse(marks.isClean(encoded: "pasted"))
        // Retry succeeds.
        _ = marks.beginSave(encoded: "pasted")
        XCTAssertTrue(marks.isClean(encoded: "pasted"))
        XCTAssertFalse(marks.shouldReseed(from: "pasted"))
    }

    func testTypingAfterFailedSaveStillSavesTheWholeBuffer() {
        // The #4285 issue asked: does typing after the paste rescue it? With
        // the rollback, the draft (paste + keystroke) is dirty as a WHOLE —
        // the next save carries the full buffer, not just the keystroke.
        var marks = ArtifactSaveWatermarks()
        marks.seed(raw: "old", encoded: "old")
        let prior = marks.beginSave(encoded: "pasted")
        marks.rollBack(to: prior)
        XCTAssertFalse(marks.isClean(encoded: "pasted plus keystroke"))
    }

    // MARK: - External updates after a failed save

    func testGenuineRemoteUpdateStillReseedsAfterFailedSave() {
        var marks = ArtifactSaveWatermarks()
        marks.seed(raw: "old", encoded: "old")
        let prior = marks.beginSave(encoded: "pasted")
        marks.rollBack(to: prior)
        // Another device really did change the stored content — reseed applies.
        XCTAssertTrue(marks.shouldReseed(from: "remote edit"))
    }
}
