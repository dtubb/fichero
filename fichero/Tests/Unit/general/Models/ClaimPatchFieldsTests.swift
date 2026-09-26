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

    private func inline(
        subject: String? = "e1", original: String? = "e1", predicate: String = "sold", object: String = "the mine",
        timeStart: String = "", timeEnd: String = "", timePrecision: String = ""
    ) -> ClaimPatchFields {
        .inline(
            subjectEntityId: subject, originalSubjectEntityId: original, predicate: predicate, object: object,
            sourcePageLabel: "p. 4", claimType: "assertion", epistemicStatus: "asserted",
            timeStart: timeStart, timeEnd: timeEnd, timePrecision: timePrecision
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
        .sheet(
            text: text, subject: subject, predicate: predicate, object: "the mine", sourcePageLabel: "",
            claimType: "assertion", epistemicStatus: "asserted"
        )
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
}
