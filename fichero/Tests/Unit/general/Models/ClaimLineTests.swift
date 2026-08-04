@testable import Fichero
import Foundation
import Testing

/// #4393 part 1: three claims about Adolfo Hurtado rendered his name on every
/// line, and twice on the first.
///
/// A claim is a triple and the subject is constant across an entity's digest,
/// so printing it per row spends the narrowest space in the app on the one word
/// the reader already knows. The doubling had a second cause: with no typed
/// triple the composer fell back to `claim.text`, the flattened sentence with
/// the subject embedded.
///
/// Scoping first established that the record is a real triple — `subject_canonical`,
/// `predicate_verb`, `object_phrase` and the `svo_*` fields all persist — so
/// this is a presentation fix, not a record fix.
struct ClaimLineTests {

    private func line(
        subject: String? = "Adolfo Hurtado",
        verb: String? = "compareció ante",
        object: String? = "Juan Catarino Asprilla",
        fallback: String = "",
        groupSubject: String? = "Adolfo Hurtado"
    ) -> String {
        ClaimLine.text(
            subject: subject, verb: verb, object: object,
            fallback: fallback, groupSubject: groupSubject
        )
    }

    // MARK: - The defect, stated directly

    @Test("the group's subject is not repeated on every row")
    func groupSubjectIsNotRepeated() {
        let rendered = line()
        #expect(!rendered.contains("Adolfo Hurtado"))
        #expect(rendered == "compareció ante · Juan Catarino Asprilla")
    }

    /// The rule is "omit when it equals the group subject", never "always
    /// omit": a claim about someone else that mentions this entity must still
    /// say who it is about, or the row asserts the wrong thing.
    @Test("a different subject is still shown")
    func differentSubjectIsShown() {
        let rendered = line(subject: "Juan Catarino Asprilla")
        #expect(rendered.hasPrefix("Juan Catarino Asprilla"))
    }

    /// Out of any list context — the delete confirmation — the subject is what
    /// identifies the claim and must survive.
    @Test("with no grouping, the subject is kept")
    func noGroupingKeepsTheSubject() {
        let rendered = line(groupSubject: nil)
        #expect(rendered.hasPrefix("Adolfo Hurtado"))
    }

    // MARK: - The doubled first line

    /// The fallback path: no triple, and `claim.text` begins with the subject.
    @Test("a fallback line does not repeat the subject it starts with")
    func fallbackDoesNotRepeatTheSubject() {
        let rendered = line(
            subject: nil, verb: nil, object: nil,
            fallback: "Adolfo Hurtado Notario público del Circuito de San Juan"
        )
        #expect(rendered == "Notario público del Circuito de San Juan")
    }

    /// A subject cannot be reliably stripped from a sentence in general, so
    /// this only removes an exact leading match and leaves every other
    /// occurrence alone rather than guessing.
    @Test("only a leading subject is stripped, never one mid-sentence")
    func onlyLeadingSubjectIsStripped() {
        let rendered = line(
            subject: nil, verb: nil, object: nil,
            fallback: "el notario Adolfo Hurtado compareció"
        )
        #expect(rendered == "el notario Adolfo Hurtado compareció")
    }

    /// Stripping must never empty the row: text that IS just the subject keeps
    /// it, because a blank row reads as a rendering bug.
    @Test("a line that is only the subject is not emptied")
    func subjectOnlyLineSurvives() {
        #expect(line(subject: nil, verb: nil, object: nil, fallback: "Adolfo Hurtado")
            == "Adolfo Hurtado")
    }

    // MARK: - Nothing renders blank

    @Test("a claim with nothing at all still renders something")
    func emptyClaimStillRenders() {
        #expect(line(subject: nil, verb: nil, object: nil, fallback: "") == ClaimLine.placeholder)
        #expect(line(subject: "", verb: "", object: "", fallback: "   ") == ClaimLine.placeholder)
    }

    /// A partial triple is still better than the flattened sentence.
    @Test("a partial triple renders without falling back")
    func partialTripleRenders() {
        #expect(line(verb: nil, fallback: "IGNORED") == "Juan Catarino Asprilla")
        #expect(line(object: nil, fallback: "IGNORED") == "compareció ante")
    }

    /// The property that matters: whatever the inputs, the group subject never
    /// appears twice in one line.
    @Test("no input renders the group subject twice")
    func groupSubjectNeverAppearsTwice() {
        let subject = "Adolfo Hurtado"
        let fallbacks = [
            "Adolfo Hurtado Adolfo Hurtado Notario público",
            "Adolfo Hurtado compareció",
            "",
            "unrelated text"
        ]
        for fallback in fallbacks {
            for verb in [nil, "compareció"] as [String?] {
                let rendered = ClaimLine.text(
                    subject: subject, verb: verb, object: nil,
                    fallback: fallback, groupSubject: subject
                )
                let occurrences = rendered.components(separatedBy: subject).count - 1
                #expect(occurrences <= 1, Comment(rawValue: "\(occurrences)x in: \(rendered)"))
            }
        }
    }

    // MARK: - Matching

    /// `subject_canonical` and an entity's `canonical_name` are normalised
    /// independently and differ in case or accent more often than in content.
    @Test("subject matching ignores case, accents and surrounding space")
    func subjectMatchingIsForgiving() {
        #expect(ClaimLine.matches("adolfo hurtado", "Adolfo Hurtado"))
        #expect(ClaimLine.matches("Adolfo Hurtado", "  Adolfo Hurtado  "))
        #expect(ClaimLine.matches("Adolfo Hurtádo", "Adolfo Hurtado"))
        #expect(!ClaimLine.matches("Juan Asprilla", "Adolfo Hurtado"))
        #expect(!ClaimLine.matches("Adolfo", nil))
    }
}
