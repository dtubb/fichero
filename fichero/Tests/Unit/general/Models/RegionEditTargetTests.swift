@testable import Fichero
import Testing

/// `source.app.edits-name-the-chosen-pass` (#4954).
///
/// Three clauses, and the third is a refusal: **with nothing shown, no edit is
/// sent.** The verbs in `ZoomableImagePreviewMac+Regions` guarded on exactly these
/// conditions already, inside view methods no test could reach — so the decision is
/// a type now and these are the tests it could not have.
///
/// What breaks if these regress: an edit lands on an artifact the person is not
/// looking at. Silently, because every verb logs only its failures and a write to
/// the wrong pass succeeds.
struct RegionEditTargetTests {

    // MARK: Clause 1 and 3 — a direct edit (move, add)

    @Test("a direct edit goes to the shown result")
    func directEditNamesTheShownArtifact() {
        #expect(RegionEditTarget.forDirectEdit(shownArtifactId: "art-shown") == "art-shown")
    }

    @Test("with nothing shown, a direct edit is refused")
    func directEditWithNothingShownIsRefused() {
        // The page has no geometry, or the load failed. An edit sent anyway lands on
        // whatever artifact the engine picks for the document — the silent write this
        // behaviour exists to prevent.
        #expect(RegionEditTarget.forDirectEdit(shownArtifactId: nil) == nil)
    }

    @Test("an empty shown id is nothing shown, not an artifact named empty")
    func emptyStringIsNotAnArtifact() {
        #expect(RegionEditTarget.forDirectEdit(shownArtifactId: "") == nil)
    }

    // MARK: Clause 1, stricter — an edit on the selection (delete, combine)

    @Test("a selection edit goes to the shown result when the selection belongs to it")
    func selectionEditNamesTheShownArtifact() {
        let target = RegionEditTarget.forSelectionEdit(
            shownArtifactId: "art-shown", selectionArtifactId: "art-shown",
            selectionCount: 1, minimumCount: 1
        )
        #expect(target == "art-shown")
    }

    @Test("a selection made against ANOTHER artifact is refused, not retargeted")
    func aStaleSelectionIsRefused() {
        // This is the clause that stops the worst version of the bug. Indices are
        // positions in ONE artifact's box list, so replaying a selection made against
        // the previous artifact deletes different boxes — a position used as an
        // identity, which is the defect `source.app.index-is-the-engines` names.
        let target = RegionEditTarget.forSelectionEdit(
            shownArtifactId: "art-now", selectionArtifactId: "art-before",
            selectionCount: 2, minimumCount: 1
        )
        #expect(target == nil)
    }

    @Test("with nothing shown, a selection edit is refused even with a selection held")
    func selectionEditWithNothingShownIsRefused() {
        let target = RegionEditTarget.forSelectionEdit(
            shownArtifactId: nil, selectionArtifactId: "art-before",
            selectionCount: 3, minimumCount: 1
        )
        #expect(target == nil)
    }

    @Test("an empty selection sends nothing")
    func anEmptySelectionSendsNothing() {
        let target = RegionEditTarget.forSelectionEdit(
            shownArtifactId: "art-shown", selectionArtifactId: "art-shown",
            selectionCount: 0, minimumCount: 1
        )
        #expect(target == nil)
    }

    @Test("combine needs two regions; one is refused")
    func combineNeedsTwo() {
        // The verbs' own arity, kept here rather than in each verb so "delete needs
        // one, combine needs two" is stated once and testable.
        let one = RegionEditTarget.forSelectionEdit(
            shownArtifactId: "art-shown", selectionArtifactId: "art-shown",
            selectionCount: 1, minimumCount: 2
        )
        let two = RegionEditTarget.forSelectionEdit(
            shownArtifactId: "art-shown", selectionArtifactId: "art-shown",
            selectionCount: 2, minimumCount: 2
        )
        #expect(one == nil)
        #expect(two == "art-shown")
    }

    @Test("a selection with no artifact of its own is refused")
    func aSelectionWithNoArtifactIsRefused() {
        let target = RegionEditTarget.forSelectionEdit(
            shownArtifactId: "art-shown", selectionArtifactId: nil,
            selectionCount: 2, minimumCount: 1
        )
        #expect(target == nil, "a selection that cannot say which artifact it is in names nothing")
    }
}
