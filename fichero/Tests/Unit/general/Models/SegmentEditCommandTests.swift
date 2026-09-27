@testable import Fichero
import Testing

/// `source.editor.set-kind`, `set-direction`, `set-language-script` (#4941), as a plan.
///
/// What these pin is the three refusals, because each is a way to send an edit to the
/// wrong place: nothing selected, a selection left over from another page, and a
/// selection whose versions are unknown — which would mean inventing an
/// `expected_version` and letting a stale edit overwrite somebody's work.
@MainActor
struct SegmentEditCommandTests {

    private func selected(
        _ ids: [String], on documentId: String = "doc-1", versions: [String: Int]? = nil
    ) -> SegmentSelection {
        let selection = SegmentSelection()
        selection.select(
            ids, documentId: documentId,
            versions: versions ?? Dictionary(uniqueKeysWithValues: ids.map { ($0, 1) })
        )
        return selection
    }

    @Test("one update per selected segment, each with the version it was selected at")
    func oneUpdatePerSegment() throws {
        let selection = selected(["seg-1", "seg-2"], versions: ["seg-1": 3, "seg-2": 7])

        let updates = try SegmentEditCommand.plan(
            .kind("heading"), for: selection, shownDocumentId: "doc-1"
        ).get()

        #expect(updates == [
            .init(segmentId: "seg-1", expectedVersion: 3, attribute: .kind("heading")),
            .init(segmentId: "seg-2", expectedVersion: 7, attribute: .kind("heading")),
        ])
    }

    @Test("with nothing selected, nothing is sent")
    func nothingSelectedIsRefused() {
        // The refusal every editor verb has and the easiest to drop: "do nothing" looks
        // correct until somebody asks why their click had no effect.
        let result = SegmentEditCommand.plan(
            .kind("line"), for: SegmentSelection(), shownDocumentId: "doc-1"
        )

        #expect(result == .failure(.nothingSelected))
    }

    @Test("a selection left over from another page is refused, not applied")
    func selectionOnAnotherPageIsRefused() {
        // The shape a stale selection takes after the person navigated away. Applying it
        // would change lines on a page they are not looking at.
        let selection = selected(["seg-1"], on: "doc-1")

        let result = SegmentEditCommand.plan(
            .direction("right-to-left"), for: selection, shownDocumentId: "doc-2"
        )

        #expect(result == .failure(.selectionIsOnAnotherPage))
    }

    @Test("with no page shown, the edit is refused rather than sent anywhere")
    func noShownPageIsRefused() {
        let result = SegmentEditCommand.plan(
            .language("la"), for: selected(["seg-1"]), shownDocumentId: nil
        )

        #expect(result == .failure(.selectionIsOnAnotherPage))
    }

    @Test("a segment with no known version refuses the WHOLE edit")
    func unknownVersionRefusesEverything() {
        // All or nothing, as with delete. Inventing an expected_version would let a stale
        // edit overwrite somebody's work; sending only the lines whose versions are known
        // would change half the selection and refuse the rest.
        let selection = selected(["seg-1", "seg-2"], versions: ["seg-1": 3])

        let result = SegmentEditCommand.plan(
            .script("Hebr"), for: selection, shownDocumentId: "doc-1"
        )

        #expect(result == .failure(.versionsUnknown))
    }

    @Test("each attribute names the segment.update field it sets")
    func attributesNameTheirFields() {
        // The route takes these exact names. A typo here is a 422 that looks like the
        // engine refusing the VALUE, which would send somebody looking in the wrong place.
        #expect(SegmentEditCommand.Attribute.kind("x").field == "kind")
        #expect(SegmentEditCommand.Attribute.direction("x").field == "direction")
        #expect(SegmentEditCommand.Attribute.language("x").field == "language")
        #expect(SegmentEditCommand.Attribute.script("x").field == "script")
        #expect(SegmentEditCommand.Attribute.furniture(true).field == "is_furniture")
    }

    @Test("values are passed through, because the engine owns the vocabulary")
    func valuesAreNotCheckedHere() throws {
        // A second copy of the direction or script vocabulary on the client is the copy
        // that drifts. The engine refuses an unknown value with a sentence naming the
        // list; this plan must not pre-empt it with a different, staler answer.
        let updates = try SegmentEditCommand.plan(
            .direction("not-a-direction"), for: selected(["seg-1"]), shownDocumentId: "doc-1"
        ).get()

        #expect(updates.first?.attribute == .direction("not-a-direction"))
    }
}

/// `source.editor.join-group` (#4941): the merge plan and its refusals.
@MainActor
struct SegmentMergePlanTests {

    private func selected(
        _ ids: [String], on documentId: String = "doc-1", versions: [String: Int]? = nil
    ) -> SegmentSelection {
        let selection = SegmentSelection()
        selection.select(
            ids, documentId: documentId,
            versions: versions ?? Dictionary(uniqueKeysWithValues: ids.map { ($0, 1) })
        )
        return selection
    }

    @Test("the first segment picked survives, and every participant sends its version")
    func firstPickedSurvives() throws {
        // The survivor's id is the one new citations use, and "the line I clicked first"
        // is the only choice the person visibly made. The merged-away ids keep forwarding
        // to it, so older citations still resolve.
        let selection = selected(["seg-2", "seg-1", "seg-3"],
                                 versions: ["seg-1": 4, "seg-2": 2, "seg-3": 9])

        let merge = try SegmentEditCommand.mergePlan(
            for: selection, shownDocumentId: "doc-1"
        ).get()

        #expect(merge.keepId == "seg-2")
        #expect(merge.segmentIds == ["seg-2", "seg-1", "seg-3"])
        #expect(merge.expectedVersions == ["seg-1": 4, "seg-2": 2, "seg-3": 9],
                "the kept segment's version is sent too")
    }

    @Test("one segment is not a join")
    func oneSegmentIsRefused() {
        // Joining a line to itself changes nothing, and sending it would put an audited
        // action that did nothing into the record a scholar reads.
        #expect(SegmentEditCommand.mergePlan(for: selected(["seg-1"]), shownDocumentId: "doc-1")
                == .failure(.needsTwoOrMore))
        #expect(SegmentEditCommand.mergePlan(for: SegmentSelection(), shownDocumentId: "doc-1")
                == .failure(.needsTwoOrMore))
    }

    @Test("a selection left over from another page is not joined")
    func anotherPageIsRefused() {
        let result = SegmentEditCommand.mergePlan(
            for: selected(["seg-1", "seg-2"], on: "doc-1"), shownDocumentId: "doc-2"
        )

        #expect(result == .failure(.selectionIsOnAnotherPage))
    }

    @Test("a participant with no known version refuses the join")
    func unknownVersionIsRefused() {
        // Merge takes a version for EVERY id, the kept one included: a concurrent edit to
        // the survivor is still something that changed since the caller last read it.
        let selection = selected(["seg-1", "seg-2"], versions: ["seg-1": 1])

        #expect(SegmentEditCommand.mergePlan(for: selection, shownDocumentId: "doc-1")
                == .failure(.versionsUnknown))
    }
}
