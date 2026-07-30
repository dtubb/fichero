@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// #4403 (P0): searching a person who demonstrably exists returned only
/// Artifacts.
///
/// Not a retrieval gap. The engine searches four legs and returns all four
/// typed; `SearchService` maps every one. But `entityHits` and `claimHits` had
/// exactly one consumer each — `.count`, feeding the empty-state reasoning —
/// while `artifactHits` alone had a renderer. The hit was found, counted, and
/// then had nowhere to go, which is why the empty state could truthfully say
/// how many entities matched while showing none of them.
///
/// These tests pin the mapping every leg now shares.
struct SearchHitPresentationTests {

    private func entity(
        id: String? = "e1",
        name: String = "Ann Marshall",
        type: Components.Schemas.EntityTypeOutput? = .person,
        sourceDocumentIds: [String]? = ["doc-1"]
    ) -> Components.Schemas.SearchEntityHit {
        Components.Schemas.SearchEntityHit(
            id: id,
            canonicalName: name,
            entityType: type,
            sourceDocumentIds: sourceDocumentIds
        )
    }

    private func claim(
        id: String? = "c1",
        text: String = "The diaries were bound in 1897.",
        sourceDocumentId: String? = "doc-1"
    ) -> Components.Schemas.SearchClaimHit {
        Components.Schemas.SearchClaimHit(
            id: id,
            text: text,
            sourceDocumentId: sourceDocumentId
        )
    }

    // MARK: - The defect, stated directly

    /// The reported case: a person is searched, the engine returns them, and
    /// the client must produce a row. Before this, no row existed at all.
    @Test("an entity hit becomes a row the user can see")
    func entityHitBecomesARow() {
        let rows = SearchHitPresentation.entityRows([entity()])

        #expect(rows.count == 1)
        #expect(rows[0].title == "Ann Marshall")
        #expect(rows[0].badge == "Person")
        #expect(rows[0].isOpenable)
    }

    @Test("a claim hit becomes a row too")
    func claimHitBecomesARow() {
        let rows = SearchHitPresentation.claimRows([claim()])

        #expect(rows.count == 1)
        #expect(rows[0].title == "The diaries were bound in 1897.")
        #expect(rows[0].badge == "Claim")
        #expect(rows[0].documentId == "doc-1")
    }

    /// Every leg maps, and none of them silently drops a hit. A leg that
    /// returns rows for some inputs and nothing for others is how this defect
    /// looked from outside.
    @Test("no leg drops a hit it was given")
    func noLegDropsAHit() {
        #expect(SearchHitPresentation.entityRows([entity(), entity(id: "e2")]).count == 2)
        #expect(SearchHitPresentation.claimRows([claim(), claim(id: "c2")]).count == 2)
        #expect(SearchHitPresentation.artifactRows([
            Components.Schemas.SearchArtifactHit(
                documentId: "d1", documentName: "Scan", artifactType: "transcription", snippet: "x"
            )
        ]).count == 1)
    }

    /// Ranking is the engine's; the client must not reorder it.
    @Test("the engine's ranking is preserved")
    func rankingIsPreserved() {
        let rows = SearchHitPresentation.entityRows([
            entity(id: "first", name: "Zed"),
            entity(id: "second", name: "Ann")
        ])
        #expect(rows.map(\.id) == ["first", "second"])
    }

    // MARK: - Identity

    /// Rows are identified by the server's id, never by array position:
    /// results re-rank between queries, and positional identity re-renders
    /// every row and mis-animates the group.
    @Test("row identity comes from the server id")
    func rowIdentityComesFromTheServer() {
        #expect(SearchHitPresentation.entityRows([entity(id: "abc")])[0].id == "abc")
        #expect(SearchHitPresentation.claimRows([claim(id: "xyz")])[0].id == "xyz")
    }

    /// An id-less hit still needs a stable, unique key — SwiftUI's `ForEach`
    /// collapses duplicate ids, which would silently hide rows.
    @Test("id-less hits still get distinct keys")
    func idLessHitsGetDistinctKeys() {
        let rows = SearchHitPresentation.entityRows([
            entity(id: nil, name: "Ann"),
            entity(id: nil, name: "Ann")
        ])
        #expect(rows.count == 2)
        #expect(rows[0].id != rows[1].id, "duplicate ids would drop a visible row")
    }

    // MARK: - A row that cannot act says so

    /// "A half-working affordance is worse than an absent one." An entity with
    /// no recorded source document must not look clickable.
    @Test("a hit with no document behind it is not openable")
    func hitWithoutADocumentIsNotOpenable() {
        let noSources = SearchHitPresentation.entityRows([entity(sourceDocumentIds: nil)])[0]
        #expect(!noSources.isOpenable)
        #expect(noSources.documentId == nil)

        let empty = SearchHitPresentation.entityRows([entity(sourceDocumentIds: [])])[0]
        #expect(!empty.isOpenable)

        let claimless = SearchHitPresentation.claimRows([claim(sourceDocumentId: nil)])[0]
        #expect(!claimless.isOpenable)
    }

    /// It is still rendered — an unopenable hit is a result, not a non-result.
    /// Hiding it would reproduce this issue for a narrower case.
    @Test("an unopenable hit is still shown, with a reason available")
    func unopenableHitIsStillShown() {
        let rows = SearchHitPresentation.entityRows([entity(sourceDocumentIds: nil)])
        #expect(rows.count == 1)
        #expect(rows[0].title == "Ann Marshall")
        #expect(!SearchHitPresentation.unopenableReason.isEmpty)
    }

    // MARK: - Nothing renders blank

    /// A row with an empty title is indistinguishable from a rendering bug.
    @Test("no row is ever blank, whatever the payload")
    func noRowIsEverBlank() {
        let blankEntity = SearchHitPresentation.entityRows([entity(name: "   ")])[0]
        #expect(!blankEntity.title.isEmpty)
        #expect(!blankEntity.badge.isEmpty)

        let blankClaim = SearchHitPresentation.claimRows([claim(text: "  \n ")])[0]
        #expect(!blankClaim.title.isEmpty)

        let typeless = SearchHitPresentation.entityRows([entity(type: nil)])[0]
        #expect(typeless.badge == "Entity", "an empty capsule reads as a broken row")
    }

    /// A claim's text carries hard returns from the source; a row is one line.
    @Test("a multi-line claim renders as one line")
    func multiLineClaimIsFlattened() {
        let row = SearchHitPresentation.claimRows([claim(text: "first line\nsecond line")])[0]
        #expect(!row.title.contains("\n"))
        #expect(row.title == "first line second line")
    }

    @Test("every entity type produces a readable badge")
    func everyEntityTypeHasAReadableBadge() {
        for type in Components.Schemas.EntityTypeOutput.allCases {
            let badge = SearchHitPresentation.entityBadge(entity(type: type))
            #expect(!badge.isEmpty, Comment(rawValue: type.rawValue))
            #expect(!badge.contains("_"), Comment(rawValue: badge))
        }
    }

    // MARK: - Structural: no leg can be unrepresented again

    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// The whole point of the fix: all three non-document legs are rendered,
    /// through one section type. This is the assertion that fails if a future
    /// leg is counted but not shown.
    @Test("every non-document leg is rendered")
    func everyLegIsRendered() throws {
        let source = try Self.appSource("Views/Shell/ContentView/ContentView+SearchResults.swift")
        for leg in ["artifactRows(stats.artifactHits)",
                    "entityRows(stats.entityHits)",
                    "claimRows(stats.claimHits)"] {
            #expect(source.contains(leg), Comment(rawValue: leg))
        }
        #expect(source.components(separatedBy: "SearchHitSection(").count - 1 == 3)
    }

    /// The dead overflow count is gone: the section expands instead of telling
    /// the user about results it will not show — this issue in miniature.
    @Test("the overflow count is actionable, not decorative")
    func overflowIsActionable() throws {
        let source = try Self.appSource("Views/Shell/ContentView/SearchHitSection.swift")
        #expect(source.contains("Button(\"Show \\(hiddenCount) more\")"))
        #expect(!source.contains("…and \\(artifactHits.count - 5) more"))
        // And identity is not positional.
        #expect(!source.contains("id: \\.offset"))
    }
}
