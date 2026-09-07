@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The entity editor's grouped-prose view (`EntitySourceGroupsView`) rendered
/// claims as dense, unclickable prose — the last claim surface you could not get
/// back to the page from. Each clause IS a claim that knows its page, so each
/// sourced clause must become a door to its source, reusing the existing
/// `ClaimSourceRequest` / `ClaimSourceNavigationState` cursor rather than a new
/// nav path (Daniel, 2026-09-04: "a statement must lead to its source").
///
/// The precision rule holds here too: a clause with no honest destination stays
/// plain — a link that goes nowhere is worse than no link.
struct EntitySourceGroupsLinkTests {

    private func claim(
        id: String?,
        documentId: String?,
        charStart: Int? = 10,
        charEnd: Int? = 40,
        text: String = "compareció ante el notario"
    ) -> Components.Schemas.KnowledgeClaim {
        Components.Schemas.KnowledgeClaim(
            id: id,
            text: text,
            sourceDocumentId: documentId,
            sourcePageLabel: "4",
            sourceCharStart: charStart,
            sourceCharEnd: charEnd
        )
    }

    /// Claim ids carried by in-prose links using the view's internal scheme.
    private func linkedClaimIds(_ attributed: AttributedString) -> [String] {
        attributed.runs.compactMap { run in
            guard let link = run.link,
                  link.scheme == EntitySourceGroupsView.claimLinkScheme
            else { return nil }
            return link.host
        }
    }

    @Test("a claim with a recorded span becomes a tappable clause linking to its source")
    func spanClaimIsLinked() throws {
        let attributed = try #require(
            EntitySourceGroupsView.buildClauseAttributedString([claim(id: "claim-1", documentId: "doc-1")])
        )
        #expect(linkedClaimIds(attributed) == ["claim-1"])
    }

    @Test("a claim with no source document stays plain prose — no dead link")
    func unsourcedClaimHasNoLink() throws {
        let attributed = try #require(
            EntitySourceGroupsView.buildClauseAttributedString([claim(id: "claim-2", documentId: nil)])
        )
        #expect(linkedClaimIds(attributed).isEmpty)
    }

    @Test("only the sourced clauses in a mixed group carry links")
    func mixedGroupLinksOnlySourced() throws {
        let claims = [
            claim(id: "a", documentId: "doc-1"),
            claim(id: "b", documentId: nil),
            claim(id: "c", documentId: "doc-2")
        ]
        let attributed = try #require(EntitySourceGroupsView.buildClauseAttributedString(claims))
        #expect(Set(linkedClaimIds(attributed)) == ["a", "c"])
    }

    @Test("empty-text claims are skipped, not padded")
    func emptyTextSkipped() {
        #expect(
            EntitySourceGroupsView.buildClauseAttributedString(
                [claim(id: "x", documentId: "doc-1", text: "")]
            ) == nil
        )
    }
}
