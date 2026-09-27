//
//  ClaimPatchFieldsTests.swift
//  FicheroTests
//
//  #4833 (`kg.read.editor-saves-through-the-audited-action`): what the two claim editors send
//  when they save. Replaces the source scrapes InlineClaimEditorTests / EditClaimSheetTests
//  (#5052) with assertions on the real payload both editors now build through one definition.
//

@testable import Fichero
import FicheroAPIClient
import Testing

struct ClaimPatchFieldsTests {
    // MARK: - Per-sentence (inline) editor

    private func draft(
        subject: String? = "e1", predicate: String = "sold", object: String = "the mine",
        timeStart: String = "", timeEnd: String = "", timePrecision: String = ""
    ) -> ClaimDraft {
        ClaimDraft(
            text: "", subject: "Ana", subjectEntityId: subject, predicate: predicate, object: object,
            sourcePageLabel: "p. 4", claimType: "assertion", epistemicStatus: "asserted",
            timeStart: timeStart, timeEnd: timeEnd, timePrecision: timePrecision
        )
    }

    private func inline(
        subject: String? = "e1", original: String? = "e1", predicate: String = "sold", object: String = "the mine",
        timeStart: String = "", timeEnd: String = "", timePrecision: String = ""
    ) -> ClaimPatchFields {
        .inline(
            draft(subject: subject, predicate: predicate, object: object,
                  timeStart: timeStart, timeEnd: timeEnd, timePrecision: timePrecision),
            originalSubjectEntityId: original
        )
    }

    @Test("the inline editor never sends a subject NAME, only an entity id")
    func inlineNeverSendsASubjectName() {
        #expect(inline(subject: "e2").subjectCanonical == nil)
    }

    @Test("the subject id is sent only when the picker changed it")
    func subjectIdSentOnlyOnAChange() {
        #expect(inline(subject: "e2", original: "e1").subjectEntityId == "e2")
        #expect(inline(subject: "e1", original: "e1").subjectEntityId == nil)
        #expect(inline(subject: nil, original: "e1").subjectEntityId == nil)
    }

    @Test("date fields are trimmed, and empty ones are not sent")
    func dateFieldsTrimmedOrOmitted() {
        let fields = inline(timeStart: " 1933-01-31 ", timeEnd: "   ", timePrecision: "day")
        #expect(fields.timeStart == "1933-01-31")
        #expect(fields.timeEnd == nil)
        #expect(fields.timePrecision == "day")
    }

    @Test("the inline editor sends no free text")
    func inlineSendsNoText() {
        #expect(inline().text == nil)
    }

    // MARK: - Full sheet

    private func sheet(text: String = "  Ana sold the mine.  ", subject: String = " Ana ", predicate: String = " ") -> ClaimPatchFields {
        .sheet(ClaimDraft(
            text: text, subject: subject, subjectEntityId: nil, predicate: predicate, object: "the mine",
            sourcePageLabel: "", claimType: "assertion", epistemicStatus: "asserted",
            timeStart: "", timeEnd: "", timePrecision: ""
        ))
    }

    @Test("the sheet trims its text and sends the typed subject name")
    func sheetTrimsAndSendsTheSubjectName() {
        let fields = sheet()
        #expect(fields.text == "Ana sold the mine.")
        #expect(fields.subjectCanonical == "Ana")
        #expect(fields.subjectEntityId == nil)
    }

    @Test("blank fields are omitted, never sent as empty strings")
    func blankFieldsAreOmitted() {
        let fields = sheet()
        #expect(fields.predicateVerb == nil)
        #expect(fields.sourcePageLabel == nil)
        #expect(fields.timeStart == nil)
    }

    // MARK: - The draft an editor opens on

    @Test("a draft opens on the claim's own values, with the editors' defaults where it has none")
    func draftOpensOnTheClaim() {
        var claim = Components.Schemas.KnowledgeClaim(id: "c1", text: "Ana sold the mine.")
        claim.subjectCanonical = "Ana"
        claim.subjectEntityId = "e1"
        claim.timeStart = "1933-01-31"
        let opened = ClaimDraft(claim: claim)
        #expect(opened.text == "Ana sold the mine.")
        #expect(opened.subject == "Ana")
        #expect(opened.subjectEntityId == "e1")
        #expect(opened.timeStart == "1933-01-31")
        #expect(opened.predicate == "")
        // Both editors default an unclassified claim the same way, and only here.
        #expect(opened.claimType == "claim")
        #expect(opened.epistemicStatus == "tentative")
    }

    @Test("an untouched draft sends no subject change, whichever editor sends it")
    func untouchedDraftChangesNoSubject() {
        var claim = Components.Schemas.KnowledgeClaim(id: "c1", text: "t")
        claim.subjectEntityId = "e1"
        let opened = ClaimDraft(claim: claim)
        #expect(ClaimPatchFields.inline(opened, originalSubjectEntityId: "e1").subjectEntityId == nil)
    }
}
