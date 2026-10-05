import Observation

// MARK: - ReaderSearchMatchState
//
// The library-search MATCH the reader's transcript should light: the page the
// hit is on (the anchor's own document) and the PAGE-RELATIVE char ranges of
// EVERY matched passage on it (from `transcript_excerpts[].anchor`, per the
// engine's `_build_transcript_excerpts`), one of them current (#5466).
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
// this the same way and runs `DocumentKGPaneRoute.pageHitsScript`, which
// lights the hits through the find bar's one "all hits + current" rule.
@MainActor
@Observable
final class ReaderSearchMatchState {
    static let shared = ReaderSearchMatchState()

    /// The transcript article to light: the search hit's own document id, which
    /// names its `<article data-page-id>`. `nil` = nothing to light (no search,
    /// or the selection is not a resolvable hit) → the coordinator clears the marks.
    private(set) var pageId: String?
    /// EVERY hit the search found on that page (#5466), PAGE-relative offsets
    /// (into that page's `page_content`), in page order. All are lit together.
    private(set) var spans: [ReaderHitSpan] = []
    /// 0-based index into `spans` of the CURRENT hit — lit stronger and
    /// scrolled to; the others stay lit.
    private(set) var currentIndex = 0

    /// A change token so the coordinator only re-issues the JS when the hits or
    /// the current one moved — `nil` when nothing is lit.
    var signature: String? {
        guard let pageId, !spans.isEmpty else { return nil }
        let list = spans.map { "\($0.start)-\($0.end)" }.joined(separator: ",")
        return "\(pageId):\(list)@\(currentIndex)"
    }

    /// Light `spans` on `pageId`, the one at `current` current. Empty or
    /// inverted spans are dropped; the rest are kept in page order.
    func set(pageId: String, spans: [ReaderHitSpan], current: Int = 0) {
        let kept = spans.filter { $0.end > $0.start }.sorted { $0.start < $1.start }
        self.pageId = pageId
        self.spans = kept
        currentIndex = min(max(0, current), max(0, kept.count - 1))
    }

    func clear() {
        pageId = nil
        spans = []
        currentIndex = 0
    }
}

/// One search hit on a page: PAGE-relative `[start, end)` offsets.
struct ReaderHitSpan: Equatable, Sendable {
    let start: Int
    let end: Int
}
