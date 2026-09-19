@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// A statement leads to its source; a name leads to everything (#4672).
///
/// Daniel, 2026-09-04: clicking an SVO statement in the biography or entity
/// editor must land on the source with the passage lit; the inspector must
/// show the quote a statement is drawn from; a person's name must lead to
/// every source that mentions them. The plumbing existed — the typed source
/// cursor, the passage latch, the scoped search — but three surfaces never
/// called it, called the wrong bus, or overrode the fixed path with the
/// broken one. See agent-work/design/entity-clickthrough-fabel-review.md.
@MainActor
struct EntityClickthroughTests {

    // MARK: - Biography sentences are claims, not prose soup

    /// `subject` defaults non-nil (#4835 requires a COMPLETE SVO triple via
    /// `ClaimSummaryCard.svoTriple(for:)`) so existing callers that only care
    /// about verb/object skip logic keep getting a renderable claim; tests
    /// that care about the subject pass their own.
    private func claim(
        id: String? = "c1", subject: String? = "Andrés", verb: String? = "otorgó", object: String? = "poder"
    ) -> Components.Schemas.KnowledgeClaim {
        var value = Components.Schemas.KnowledgeClaim(id: id, text: "t")
        value.subjectCanonical = subject
        value.predicateVerb = verb
        value.objectPhrase = object
        return value
    }

    /// #4835: each sentence uses the CLAIM'S OWN subject, never a pronoun and
    /// never the page entity's name. The second claim's subject deliberately
    /// differs from the first — proving the fix, since the OLD code would
    /// have rendered "they compareció ante mí" here regardless of whose
    /// claim it actually was.
    @Test("each biography sentence uses the claim's own subject, never a pronoun")
    func sentencesUseTheClaimsOwnSubject() {
        let pairs = EntityDigestContent.biographySentences(
            claims: [
                claim(id: "a", subject: "Andrés"),
                claim(id: "b", subject: "Pedro Mosquera", verb: "compareció", object: "ante mí")
            ]
        )
        #expect(pairs.count == 2)
        #expect(pairs[0].sentence == "Andrés otorgó poder.")
        #expect(pairs[0].claim.id == "a")
        #expect(pairs[1].sentence == "Pedro Mosquera compareció ante mí.")
        #expect(pairs[1].claim.id == "b")
    }

    @Test("a claim with neither verb nor object produces no sentence")
    func emptyVerbAndObjectClaimsAreSkippedNotPadded() {
        let pairs = EntityDigestContent.biographySentences(
            claims: [claim(id: "empty", verb: nil, object: nil), claim(id: "real")]
        )
        #expect(pairs.count == 1)
        #expect(pairs[0].claim.id == "real")
    }

    /// #4835: a claim missing its OWN subject is skipped, not rendered with a
    /// guessed one — `ClaimSummaryCard.svoTriple(for:)` returns `nil` for an
    /// incomplete triple, which is the honest fallback this reuses rather
    /// than inventing a second one.
    @Test("a claim with an empty subject is skipped, not given a guessed one")
    func emptySubjectClaimsAreSkipped() {
        let pairs = EntityDigestContent.biographySentences(
            claims: [claim(id: "no-subject", subject: nil), claim(id: "after")]
        )
        #expect(pairs.count == 1)
        #expect(pairs[0].claim.id == "after")
    }

    /// #4835's actual bug report: on the OBJECT's own digest page, the claim
    /// must still say who really did it — never substitute the page entity.
    @Test("a claim where the page entity is the OBJECT still renders the TRUE subject")
    func objectSideClaimRendersTrueSubject() {
        let pairs = EntityDigestContent.biographySentences(
            claims: [claim(
                id: "sale", subject: "Andrés Restrepo",
                verb: "sold the mine to", object: "Pedro Mosquera"
            )]
        )
        #expect(pairs.count == 1)
        #expect(pairs[0].sentence == "Andrés Restrepo sold the mine to Pedro Mosquera.")
        #expect(!pairs[0].sentence.hasPrefix("Pedro Mosquera"))
    }

    @Test("no biography sentence ever falls back to the pronoun 'they'")
    func noSentenceContainsThePronoun() {
        let pairs = EntityDigestContent.biographySentences(
            claims: [
                claim(id: "a", subject: "Andrés"),
                claim(id: "b", subject: "Pedro Mosquera", verb: "compareció", object: "ante mí"),
                claim(id: "c", subject: "María López", verb: "otorgó", object: "testamento")
            ]
        )
        #expect(pairs.allSatisfy { !$0.sentence.contains("they") })
    }

    /// Source-scan companion to the behavioral tests above: the literal
    /// string is gone from the function body, not merely unreachable.
    @Test("biographySentences' body contains no hard-coded pronoun literal")
    func biographySentencesSourceHasNoHardCodedPronoun() throws {
        let digest = try AppSource.code("Views/Inspector/Knowledge/EntityDigestView.swift")
        let start = try #require(digest.range(of: "static func biographySentences"))
        let bodyEnd = try #require(digest.range(of: "\n    }", range: start.upperBound..<digest.endIndex))
        let body = digest[start.upperBound..<bodyEnd.lowerBound]
        #expect(!body.contains("\"they\""))
    }

    // MARK: - The three repaired click paths call the cursor

    @Test("the biography renders per-sentence claim links, not one dead blob")
    func biographyIsClickable() throws {
        let digest = try AppSource.code("Views/Inspector/Knowledge/EntityDigestView.swift")
        #expect(digest.contains("biographyAttributed"))
        #expect(digest.contains("OpenURLAction"))
        // The handler must land on the shared cursor — the same bus the
        // provenance rows post to — not a second addressing scheme.
        #expect(digest.contains("claimSourceNavigationState?.request(request)"))
    }

    @Test("the digest header's name leads to every source, like #882's")
    func digestNameFiresScopedSearch() throws {
        let digest = try AppSource.code("Views/Inspector/Knowledge/EntityDigestView.swift")
        let header = try #require(
            digest.components(separatedBy: "private var headerSection").dropFirst().first
        )
        #expect(String(header.prefix(1200)).contains("entitySearchState?.request("))
    }

    // `ontologyClosurePostsTheSourceRequest` DELETED (#4705 increment 3): it
    // read `OntologyBrowser+Detail.swift`, which is gone with the KG sidebar
    // mode's own entity-detail panel. The #4666 defect class it pinned
    // (focus-without-navigate) is still covered for the surviving
    // click-through surfaces by this file's other tests.

    // MARK: - Attestations are navigable, not just counted (#4672)

    private func multiSourceClaim() -> Components.Schemas.KnowledgeClaim {
        var row = Components.Schemas.KnowledgeClaim(id: "c9", text: "t")
        row.sourceDocumentId = "doc-primary"
        row.sourcePageLabel = "533r"
        row.sourceExcerpt = "otorgamos poder cumplido"
        row.sourceCharStart = 61
        row.sourceCharEnd = 101
        row.sourceIds = ["doc-second", "doc-primary", "doc-third", ""]
        row.sourcePageLabels = ["12v"]
        return row
    }

    @Test("every attested place becomes a row, primary first with its quote")
    func attestationRowsCarryTheirAnchors() {
        let rows = ClaimSummaryCard.attestations(for: multiSourceClaim())
        // doc-primary repeated in sourceIds is one attestation, not two;
        // the empty id is nothing at all.
        #expect(rows.map(\.documentId) == ["doc-primary", "doc-second", "doc-third"])
        #expect(rows[0].isPrimary)
        #expect(rows[0].quote == "otorgamos poder cumplido")
        #expect(rows[0].charStart == 61)
        // Pages zip index-wise with their source ids; a missing label is
        // nil, never invented.
        #expect(rows[1].pageLabel == "12v")
        #expect(rows[2].pageLabel == nil)
        // Only the primary anchor exists in the model — additional rows must
        // not claim offsets or quotes they do not have.
        #expect(rows[1].quote == nil)
        #expect(rows[1].charStart == nil)
    }

    @Test("a single-source claim is one attestation, so no list renders")
    func singleSourceStaysSingle() {
        var row = Components.Schemas.KnowledgeClaim(id: "c1", text: "t")
        row.sourceDocumentId = "doc-only"
        #expect(ClaimSummaryCard.attestations(for: row).count == 1)
        // No source at all (a manually-asserted claim, #2019) → no rows.
        #expect(ClaimSummaryCard.attestations(
            for: Components.Schemas.KnowledgeClaim(id: "c2", text: "t")
        ).isEmpty)
    }

    @Test("also-extracted-by is attribution: labels come through, junk does not")
    func alsoExtractedByParses() throws {
        var row = Components.Schemas.KnowledgeClaim(id: "c3", text: "t")
        #expect(ClaimSummaryCard.alsoExtractedBy(row) == nil)
        row.metadata = .init(additionalProperties: try .init(
            unvalidatedValue: ["also_extracted_by": ["apple/apple-intelligence", ""]]
        ))
        #expect(ClaimSummaryCard.alsoExtractedBy(row) == ["apple/apple-intelligence"])
    }

    @Test("each attestation row navigates to ITS page, not always the primary")
    func attestationRowsNavigateIndividually() throws {
        let details = try AppSource.code(
            "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift"
        )
        let list = try #require(
            details.components(separatedBy: "var attestationList: some View").dropFirst().first
        )
        let body = String(list.prefix(2500))
        #expect(body.contains("documentId: attestation.documentId"))
        #expect(body.contains("claimSourceNavigationState?.request(request)"))
    }

    @Test("the provenance badges open the drawer where the evidence lives")
    func badgesAreADoor() throws {
        let details = try AppSource.code(
            "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift"
        )
        let badges = try #require(
            details.components(separatedBy: "var provenanceBadges: some View").dropFirst().first
        )
        #expect(String(badges.prefix(1200)).contains("isExpanded = true"))
    }

    // MARK: - Corroborating runs are evidence, not a log (0f6feeccc)

    @Test("the same model on two pages is two corroborations, never collapsed")
    func corroborationsKeepEveryRow() throws {
        var row = Components.Schemas.KnowledgeClaim(id: "c5", text: "t")
        row.metadata = .init(additionalProperties: try .init(unvalidatedValue: [
            "corroborations": [
                ["provider": "apple", "model": "apple-intelligence",
                 "document_id": "doc-a", "page_label": "533r",
                 "char_start": 10, "char_end": 40],
                ["provider": "apple", "model": "apple-intelligence",
                 "document_id": "doc-a", "page_label": "534v"],
            ],
            "also_extracted_by": ["apple/apple-intelligence", "openrouter/gemini-flash-lite"],
        ]))
        let rows = ClaimSummaryCard.corroborations(for: row)
        // Two anchored rows for the same model — the commonest corroboration
        // of all — plus ONE legacy label the anchored rows don't cover. The
        // covered label must not double-render as a third apple row.
        #expect(rows.count == 3)
        #expect(rows[0].pageLabel == "533r")
        #expect(rows[0].charStart == 10)
        #expect(rows[0].isNavigable)
        #expect(rows[1].pageLabel == "534v")
        #expect(rows[1].charStart == nil)
        #expect(rows[2].label == "openrouter/gemini-flash-lite")
        #expect(!rows[2].isNavigable)
    }

    @Test("legacy claims degrade to attribution, not fake doors")
    func legacyCorroborationsAreLabelOnly() throws {
        var row = Components.Schemas.KnowledgeClaim(id: "c6", text: "t")
        row.metadata = .init(additionalProperties: try .init(
            unvalidatedValue: ["also_extracted_by": ["mlx/qwen-vl"]]
        ))
        let rows = ClaimSummaryCard.corroborations(for: row)
        #expect(rows.count == 1)
        #expect(rows[0].label == "mlx/qwen-vl")
        #expect(!rows[0].isNavigable)
    }

    @Test("a navigable corroboration opens ITS page through the cursor")
    func corroborationRowsNavigate() throws {
        let details = try AppSource.code(
            "Views/Library/ViewModes/Graph/Ontology/Claim/ClaimSummaryCard+Details.swift"
        )
        let section = try #require(
            details.components(separatedBy: "var corroborationSection: some View").dropFirst().first
        )
        let body = String(section.prefix(2200))
        #expect(body.contains("pageLabel: corroboration.pageLabel"))
        #expect(body.contains("claimSourceNavigationState?.request(request)"))
    }

    // MARK: - Corroboration reaches the prose

    @Test("corroboration count reads both key spellings and both types")
    func corroborationCountReads() throws {
        var row = Components.Schemas.KnowledgeClaim(id: "c", text: "t")
        #expect(EntityDigestContent.corroborationCount(of: row) == nil)
        row.metadata = .init(additionalProperties: try .init(
            unvalidatedValue: ["corroboration_count": 2]
        ))
        #expect(EntityDigestContent.corroborationCount(of: row) == 2)
        row.metadata = .init(additionalProperties: try .init(
            unvalidatedValue: ["corroborationCount": "3"]
        ))
        #expect(EntityDigestContent.corroborationCount(of: row) == 3)
    }

    @Test("the inspector quote is a door, not a query")
    func inspectorQuoteOpensTheSource() throws {
        let block = try AppSource.code("Views/Inspector/Knowledge/EntityKindRow+ClaimBlock.swift")
        let button = try #require(
            block.components(separatedBy: "private func claimExcerptButton").dropFirst().first
        )
        let body = String(button.prefix(2200))
        #expect(body.contains("claimSourceNavigationState?.request("))
        // The old behaviour fired a library text-search for the quote's own
        // words. Comment-stripped scan, so this line can't re-trip on prose.
        #expect(!body.contains("entitySearchState?.request("))
    }

    /// The FOURTH surface in this class (Daniel, 2026-09-05): double-clicking a
    /// claim row — or its "Open Source" menu — went through `openClaim`, which
    /// only focused the claim and called `onNavigateToSource`. That host handler
    /// (`navigateToSourcePage`) re-selects the source FILE in the library, so
    /// the reader landed on page 1 of the file, not the page the claim came
    /// from, with nothing lit. It must post the same source cursor the quote and
    /// the Ontology browser do.
    @Test("opening a claim row posts the source cursor, not just a file re-select")
    func claimRowOpenPostsTheSourceRequest() throws {
        let actions = try AppSource.code("Views/Inspector/Knowledge/EntityKindRow+Actions.swift")
        let openClaim = try #require(
            actions.components(separatedBy: "func openClaim(").dropFirst().first
        )
        let body = String(openClaim.prefix(1600))
        // The complete "trace to source" cursor — the reader opens the exact
        // page and lights the passage via handleOpenClaimSource.
        #expect(body.contains("claimSourceNavigationState.request(request)"))
        #expect(body.contains("sourceNavigationRequest("))
    }

    /// The ENTITY half (Daniel, 2026-09-05, option A): a name is not one page,
    /// so opening an entity traces it to source the only way a name can be —
    /// the scoped search across every mention. Was `onEntitySelect?(id)` alone,
    /// which focused the graph and navigated nowhere.
    @Test("opening an entity fires the scoped mention search, not a dead focus")
    func entityOpenFiresTheScopedMentionSearch() throws {
        let menus = try AppSource.code(
            "Views/Inspector/Knowledge/Entities/DocumentInspectorEntitiesTab+Menus.swift"
        )
        let openEntity = try #require(
            menus.components(separatedBy: "func openEntity(").dropFirst().first
        )
        let body = String(openEntity.prefix(600))
        // The mention search across all sources — the same path "Find in
        // Library" and the digest header use (postSearch → entitySearchState).
        #expect(body.contains("postSearch("))
        // It must not degrade back to focus-only, which navigated nowhere.
        #expect(!body.contains("onEntitySelect?(id)"))
    }

    /// The REACHABILITY half (Daniel, 2026-09-05, live testing: "when I click on
    /// a page, I'm not taken there"). All four repaired click paths above post to
    /// `entitySearchState` / `claimSourceNavigationState` — but those per-window
    /// buses are injected only on the NavigationSplitView subtree, and the
    /// Document Knowledge inspector lives in the `.inspector` content, which does
    /// NOT inherit the window environment (the documented non-inheritance the
    /// library-service re-injection already works around). Unless the buses are
    /// re-injected across THAT boundary too, the inspector reads them as nil and
    /// every entity/claim clickthrough is a silent no-op — the row-logic fixes
    /// land on a cursor that isn't there (#4666/#4672). This pins the injection
    /// so it can't be dropped from the re-injected list again.
    @Test("the inspector content re-injects the request buses, or clickthrough no-ops")
    func inspectorBoundaryReinjectsTheRequestBuses() throws {
        let root = try AppSource.code(
            "Views/Shell/ContentView/Layout/ContentView+RootLayout.swift"
        )
        // Scope to the inspector-content injection chain: everything the
        // `if let library` branch stacks onto `inspectorContainerView`, up to
        // the `} else {` placeholder branch. The detail-side injection lives
        // far below in `requestBusesAndAppleScript`, past this window.
        let afterServices = try #require(
            root.components(separatedBy: ".libraryServiceEnvironment(library)").dropFirst().first
        )
        let injectionBlock = try #require(
            afterServices.components(separatedBy: "} else {").first
        )
        // Both buses the inspector's openEntity/openClaim post to must cross
        // the boundary — a subset is the exact bug the services above document.
        #expect(injectionBlock.contains(".environment(entitySearchState)"))
        #expect(injectionBlock.contains(".environment(claimSourceNavigationState)"))
    }

    // MARK: - #4833: the biography's own per-sentence edit affordance

    /// A biography sentence reaches the SAME inline editor a KG digest
    /// sentence does, via a second, explicit "[Edit]" link — separate from
    /// the sentence's own reveal link.
    @Test("a biography sentence's edit link opens InlineClaimEditor")
    func biographySentenceEditOpensInlineEditor() throws {
        let source = try AppSource.text("Views/Inspector/Knowledge/EntityDigestView.swift")
        #expect(source.contains("claimEditLinkScheme"))
        #expect(source.contains("editingBiographyClaimId = claimId"))
        #expect(source.contains("InlineClaimEditor("))
    }

    /// `onSave` splices the returned claim into this view's own `claims` —
    /// never a reload; `ClaimStore.patch` does not bump `changeToken` on its
    /// own, so the existing `.onChange(of: claimStore?.changeToken)` resync
    /// would not otherwise pick this up.
    @Test("a biography edit splices the returned claim, not a reload")
    func biographyEditSplicesRatherThanReloads() throws {
        let source = try AppSource.text("Views/Inspector/Knowledge/EntityDigestView.swift")
        #expect(source.contains("spliceUpdatedClaim(updated)"))
        let body = try #require(
            source.components(separatedBy: "func spliceUpdatedClaim(").dropFirst().first
        )
        let scope = String(body.prefix(300))
        #expect(scope.contains("claims[index] = updated"))
        #expect(!scope.contains("await loadClaims()"), "a patched claim splices — it never re-triggers the network load")
    }
}
