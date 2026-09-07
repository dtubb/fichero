import Observation

// MARK: - ReaderSearchMatchState
//
// The library-search MATCH the reader's transcript should light: the page the
// hit is on (the anchor's own document) and the PAGE-RELATIVE char range of the
// matched passage (from `transcript_excerpts[].anchor`, per the engine's
// `_build_transcript_excerpts`).
//
// This is the HTML-backend highlight Daniel asked for — the exact matched span
// lit in place — replacing the old workaround that seeded the find-in-page bar
// with a snippet of the excerpt text (`ReaderPassageAnchor.findPhrase`) and
// let the substring finder light it. Substring re-scanning lit partial words
// ("nose" inside "diag-nose"); the anchor names the exact span, so the reader
// can be precise.
//
// A shared latch (not threaded through the view tree), mirroring
// `ClaimFocusState`, which the SAME transcript coordinator already reads in
// `syncSelection` to drive `scrollToSpan` for claims. The coordinator reads
// this the same way and calls `window.fichero.highlightMatchInPage`.
@MainActor
@Observable
final class ReaderSearchMatchState {
    static let shared = ReaderSearchMatchState()

    /// The transcript article to light: the search hit's own document id, which
    /// names its `<article data-page-id>`. `nil` = nothing to light (no search,
    /// or the selection is not a resolvable hit) → the coordinator clears the mark.
    private(set) var pageId: String?
    /// PAGE-relative match offsets (into that page's `page_content`).
    private(set) var charStart: Int?
    private(set) var charEnd: Int?

    /// A change token so the coordinator only re-issues the JS when the match
    /// actually moved — `nil` when nothing is lit.
    var signature: String? {
        guard let pageId, let charStart, let charEnd else { return nil }
        return "\(pageId):\(charStart):\(charEnd)"
    }

    func set(pageId: String, charStart: Int?, charEnd: Int?) {
        self.pageId = pageId
        self.charStart = charStart
        self.charEnd = charEnd
    }

    func clear() {
        pageId = nil
        charStart = nil
        charEnd = nil
    }
}
