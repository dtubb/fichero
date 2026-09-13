@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// spec: panes-magnifiers-workspaces — `panes.claim.source-is-document`.
///
/// The Claims library table's Source column must read as the source DOCUMENT's
/// name, not a raw id ("Source 2a614b56…"). The bug was that resolution only
/// consulted the folder-scoped document set, so a library-wide claim whose
/// source lives elsewhere fell back to the raw id.
///
/// The reset/resolution decision is the pure part —
/// `LibraryClaimsModel.sourceLabel(for:resolve:)` — pinned here off-main with an
/// injected resolver: a resolvable id yields the document name, an unresolvable
/// id yields a SHORT non-raw fallback (never empty, never the 32-char id), and a
/// claim with no source reads an em dash. This is a behavior test of the real
/// function, NOT a source-scrape.
struct ClaimSourceLabelTests {

    private func claim(source: String?) -> Components.Schemas.KnowledgeClaim {
        Components.Schemas.KnowledgeClaim(
            id: "c1",
            text: "Pedro travelled to Popayán.",
            sourceDocumentId: source
        )
    }

    @Test("a resolvable source id yields the document's real name")
    func resolvableYieldsName() {
        let label = LibraryClaimsModel.sourceLabel(for: claim(source: "doc-42")) { id in
            id == "doc-42" ? "Marshall Diary, p.4" : nil
        }
        #expect(label == "Marshall Diary, p.4")
    }

    @Test("an unresolvable source id yields a short, non-raw fallback (never empty)")
    func unresolvableYieldsShortFallback() {
        let rawId = "2a614b56ffffffffffffffffffffffff"
        let label = LibraryClaimsModel.sourceLabel(for: claim(source: rawId)) { _ in nil }
        // Never empty, and never the full 32-char id.
        #expect(!label.isEmpty)
        #expect(label != rawId)
        #expect(label.hasPrefix("Source "))
        #expect(!label.contains(rawId))
        // The truncated stem is the first 8 chars only.
        #expect(label.contains("2a614b56"))
    }

    @Test("a claim with no source reads an em dash, not a Source placeholder")
    func noSourceReadsDash() {
        #expect(LibraryClaimsModel.sourceLabel(for: claim(source: nil)) { _ in "x" } == "—")
        #expect(LibraryClaimsModel.sourceLabel(for: claim(source: "")) { _ in "x" } == "—")
        #expect(LibraryClaimsModel.sourceLabel(for: claim(source: "   ")) { _ in "x" } == "—")
    }

    @Test("an empty resolved name falls back to the short id, never an empty cell")
    func emptyResolvedNameFallsBack() {
        // A resolver that returns whitespace/empty must not produce an empty cell.
        let label = LibraryClaimsModel.sourceLabel(for: claim(source: "doc-42")) { _ in "   " }
        #expect(label == "Source doc-42…")
    }

    // MARK: - Click-through reuse (spec: kg-entity-inspector source.one-anchor-builder)

    /// The Source cell's click-through reuses the SAME producer the entity
    /// statements use — `ClaimSourceRequest.request(for:)` — so a claim with a
    /// recorded source yields a navigation request targeting that document. No
    /// second navigation path.
    @Test("a claim with a source document yields a source-navigation request to that document")
    func claimYieldsSourceRequest() {
        let c = Components.Schemas.KnowledgeClaim(
            id: "c1",
            text: "Pedro travelled to Popayán.",
            sourceDocumentId: "doc-42",
            sourceCharStart: 10,
            sourceCharEnd: 25
        )
        let request = ClaimSourceRequest.request(for: c)
        #expect(request?.documentId == "doc-42")
        #expect(request?.claimId == "c1")
    }

    @Test("a claim with no source has nowhere honest to navigate")
    func noSourceNoRequest() {
        let c = Components.Schemas.KnowledgeClaim(id: "c1", text: "loose text", sourceDocumentId: nil)
        #expect(ClaimSourceRequest.request(for: c) == nil)
    }
}
