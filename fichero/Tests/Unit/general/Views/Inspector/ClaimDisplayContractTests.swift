@testable import Fichero
import XCTest

/// What a claim owes the reader (#4393).
///
/// The issue is one sentence — "every claim repeats the subject and ends in a
/// bracketed internal filename" — and three separate defects. Grouping and
/// source-navigation landed in parts 1 and 2; this suite is the floor under all
/// of it, including the two halves nothing was watching: the storage filename,
/// and what an edit actually does.
///
/// Source-level where the property IS source-level (which call a view makes),
/// behavioural where a value can be computed. The alternative for the view
/// assertions is standing up SwiftUI with a live library, which tests the
/// harness more than the contract — the reasoning `ClaimStoreRoutingTests`
/// already settled.
final class ClaimDisplayContractTests: XCTestCase {

    private static let digest = "Views/Inspector/Knowledge/EntityDigestView.swift"

    // MARK: - Claims group by subject, without repeating it

    /// The digest groups under its entity and tells the composer so.
    ///
    /// The composer takes `groupSubject` as an argument precisely so the two
    /// callers can answer differently: the digest omits the subject it is
    /// grouped under, and a delete confirmation — which names one claim out of
    /// any list — keeps it. Both answers are correct, and a test that only
    /// pinned "the subject is omitted" would have made the second one a bug.
    func testTheDigestComposesEveryClaimAgainstItsGroupSubject() throws {
        let source = try AppSource.text(Self.digest)

        XCTAssertTrue(source.contains("ClaimLine.text("))
        XCTAssertTrue(
            source.contains("groupSubject: groupSubject"),
            "the digest is grouped under one entity, so its claims must omit that subject")
        XCTAssertTrue(source.contains("private var groupSubject: String? { entity.canonicalName }"))
    }

    /// The delete confirmation keeps the subject. Opposite answer, same
    /// composer, and stated here so a future "simplification" to one shared
    /// call site fails rather than quietly making the alert ambiguous.
    func testTheDeleteConfirmationKeepsTheSubject() throws {
        let source = try AppSource.text(
            "Views/Library/ViewModes/Graph/Ontology/Entity/EntityDetailView+Claims.swift")

        XCTAssertTrue(source.contains("ClaimLine.text("))
        XCTAssertTrue(
            source.contains("groupSubject: nil"),
            "an alert names one claim out of context — the subject is what identifies it")
    }

    /// The rule is "omit when it equals the group subject", never "always
    /// omit". A claim about somebody else that mentions this entity must still
    /// say who it is about, or the list asserts the wrong thing about the
    /// person whose page you are on — a fabricated fact, not a layout nit.
    func testAClaimAboutSomebodyElseKeepsItsOwnSubject() {
        let line = ClaimLine.text(
            subject: "Juan Catarino Asprilla",
            verb: "compareció ante",
            object: "Adolfo Hurtado",
            fallback: "",
            groupSubject: "Adolfo Hurtado")

        XCTAssertTrue(line.contains("Juan Catarino Asprilla"))
    }

    func testTheGroupSubjectIsDroppedWhenItIsTheClaimSubject() {
        let line = ClaimLine.text(
            subject: "Adolfo Hurtado",
            verb: "es",
            object: "Notario público del Circuito de San Juan",
            fallback: "",
            groupSubject: "Adolfo Hurtado")

        XCTAssertFalse(
            line.contains("Adolfo Hurtado"),
            "the reader is on Adolfo Hurtado's page; printing it again spends the narrowest "
                + "space in the app on the one word they already know")
        XCTAssertTrue(line.contains("Notario público del Circuito de San Juan"))
    }

    // MARK: - A claim reaches its source

    /// Selecting a claim navigates, through the SAME cursor the outline,
    /// annotations and artifacts use. Not a second navigation path (#4373).
    func testSelectingAClaimRequestsItsSourceOnTheSharedCursor() throws {
        let source = try AppSource.text(Self.digest)

        XCTAssertTrue(source.contains("ClaimSourceRequest.request(for: claim)"))
        XCTAssertTrue(source.contains("claimSourceNavigationState?.request(request)"))
    }

    // Span / region / page-only / unknown precision is pinned exhaustively by
    // `ClaimSourceRequestTests` — including the rule that matters most, that a
    // claim with no recorded span navigates to its page and draws no highlight.
    // Not repeated here: a second copy of an assertion is a second thing to
    // keep in agreement, and the two would drift.

    // MARK: - No claim renders a storage filename

    /// The bracketed internal filename, from the issue's own first line.
    ///
    /// Two defects in one citation: it was built from the STORAGE name, and it
    /// was looked up only in `currentDocuments` — so it printed an internal
    /// identifier AND vanished when that document was not loaded. A citation
    /// that changes depending on what else is on screen is worse than none.
    func testTheComposedBiographyCarriesNoBracketedFilename() throws {
        let source = try AppSource.text(Self.digest)

        XCTAssertFalse(source.contains("[\\(fileName)]"))
        XCTAssertFalse(source.contains("lastPathComponent"))
    }

    /// The claims' source header names the document the way the sidebar does.
    func testTheSourceHeaderComposesThroughDocumentTitle() throws {
        let source = try AppSource.text(Self.digest)

        XCTAssertTrue(source.contains("DocumentTitle.displayName("))
        XCTAssertFalse(
            source.contains("return doc.name"),
            "a page child's name is the engine's upload temp file (#4416)")
    }

    /// The behaviour under the source assertion: a page whose `name` is the
    /// upload temp resolves to something a historian recognises, never to the
    /// storage artifact and never to the id.
    func testAPageChildNeverShowsTheEngineUploadName() {
        let parent = Document(id: "doc:parent", name: "18590129.pdf")
        let page = Document(
            id: "doc:page",
            parentId: "doc:parent",
            docType: .page,
            name: "fichero_upload_c84fgjke.pdf")

        let shown = DocumentTitle.displayName(for: page, parent: parent)
        XCTAssertFalse(DocumentTitle.isStorageName(shown))
        XCTAssertFalse(shown.contains("fichero_upload_"))
        XCTAssertFalse(shown.contains("doc:"))
    }

    // MARK: - An edit persists, is audited, and updates one row

    /// Editing goes through the audited action layer, so the mutation names its
    /// actor (#1848 / #4415 / #4485). A claim edited by nobody in particular is
    /// not curation — it is an unattributed change to the evidence.
    func testEditingAClaimGoesThroughTheAuditedActionLayer() throws {
        let source = try AppSource.text(
            "Views/Library/ViewModes/Graph/Ontology/Claim/EditClaimSheet.swift")

        XCTAssertTrue(source.contains("invokeAction("))
        XCTAssertTrue(source.contains("name: \"claim.patch\""))
    }

    /// **The fields, not the sentence.** The issue asks for structured editing
    /// precisely so a corrected claim stays a triple — editing a rendered
    /// sentence and re-parsing it is what embeds a subject in an object string
    /// and recreates the doubling by hand.
    func testTheEditorEditsTheTripleRatherThanTheRenderedSentence() throws {
        let source = try AppSource.text(
            "Views/Library/ViewModes/Graph/Ontology/Claim/EditClaimSheet.swift")

        XCTAssertTrue(source.contains("TextField(\"Subject\", text: $subject)"))
        XCTAssertTrue(source.contains("TextField(\"Predicate\", text: $predicate)"))
        XCTAssertTrue(source.contains("TextField(\"Object\", text: $object)"))
        XCTAssertTrue(source.contains("patch.subjectCanonical"))
        XCTAssertTrue(source.contains("patch.predicateVerb"))
        XCTAssertTrue(source.contains("patch.objectPhrase"))
    }

    /// A patch updates ONE row (#4389). Not a reload: the server already
    /// returned the authoritative claim, and replacing the array re-renders
    /// every row and drops scroll position and selection at the moment the user
    /// is mid-edit. An edit that makes the list jump reads as an edit that
    /// failed.
    func testPatchingAClaimUpdatesTheRowAndNotTheWholeList() throws {
        let source = try AppSource.text("Models/ClaimStore.swift")

        let patchBody = try XCTUnwrap(source.components(separatedBy: "func patch(").last)
            .components(separatedBy: "func merge(").first

        let body = try XCTUnwrap(patchBody)
        XCTAssertTrue(
            body.contains("claims[index] = updated"),
            "the edited claim replaces itself in place")
        XCTAssertTrue(
            body.contains("firstIndex(where: { $0.id == claimId })"),
            "found by id, so the row keeps its position")
    }
}
