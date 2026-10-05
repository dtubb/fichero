#if canImport(AppKit)
@testable import Fichero
import AppKit
import Foundation
import Testing
import WebKit

/// #5466: every hit on a Reader page is lit at once, the current one stronger,
/// and the Reader has ONE rule for that — the find bar's (`__ficheroLightHits`
/// in `ReaderFindInPage.swift`). A library search's anchored hits go through
/// the same rule (`pageHitsScript`) instead of the old one-mark-at-a-time
/// `applySearchMatchHighlight`.
///
/// WHY a real `WKWebView`: the lighting is CSS Custom Highlights set by script
/// in the Reader's web view. A string check on the script would keep passing
/// if the script lit one range, or unlit the others on Next; asking WebKit how
/// many ranges each highlight holds is the behaviour the reader sees. The page
/// is the transcript markup the engine template renders (`.transcript-page`
/// with `data-page-id`, text in `.transcript-page-body`).
@MainActor
@Suite("Reader lights every hit on the page (#5466)")
struct ReaderAllHitsTests {

    // MARK: - A real web view

    private struct LoadTimedOut: Error, CustomStringConvertible {
        var description: String { "the test page never loaded — WebKit did not start, nothing was measured" }
    }

    @MainActor
    private final class LoadWatcher: NSObject, WKNavigationDelegate {
        private var resume: ((Result<Void, any Error>) -> Void)?

        func load(_ html: String, into webView: WKWebView) async throws {
            try await withCheckedThrowingContinuation { continuation in
                resume = { continuation.resume(with: $0) }
                webView.navigationDelegate = self
                webView.loadHTMLString(html, baseURL: nil)
                DispatchQueue.main.asyncAfter(deadline: .now() + 30) { [weak self] in
                    self?.finish(.failure(LoadTimedOut()))
                }
            }
        }

        private func finish(_ result: Result<Void, any Error>) {
            guard let resume else { return }
            self.resume = nil
            resume(result)
        }

        func webView(_ webView: WKWebView, didFinish navigation: WKNavigation!) { finish(.success(())) }
        func webView(_ webView: WKWebView, didFail navigation: WKNavigation!, withError error: any Error) {
            finish(.failure(error))
        }
        func webView(
            _ webView: WKWebView, didFailProvisionalNavigation navigation: WKNavigation!, withError error: any Error
        ) { finish(.failure(error)) }
    }

    /// Three "cat"s on page p1 (offsets 4, 16, 28), one on p2 — so a page-scoped
    /// hit list and a whole-document find can be told apart.
    static let pageText = "the cat and the cat and the cat"
    private static let html = """
    <!doctype html><html><head><meta charset="utf-8"></head><body>
    <div class="content"><div class="transcript" id="transcript-panel">
    <article class="transcript-page" data-page-id="p1"><div class="transcript-page-body">\(pageText)</div></article>
    <article class="transcript-page" data-page-id="p2"><div class="transcript-page-body">a cat</div></article>
    </div></div></body></html>
    """

    private let webView = WKWebView(frame: NSRect(x: 0, y: 0, width: 600, height: 400))
    private let watcher = LoadWatcher()

    private func load() async throws { try await watcher.load(Self.html, into: webView) }

    /// What WebKit holds under one highlight name: how many ranges are lit, and
    /// the start offset of each (in its text node), in order.
    private struct Lit: Equatable {
        let all: [Int]
        let current: [Int]
    }

    private func lit(_ name: String) async throws -> Lit {
        let probe = """
        (() => {
            const starts = (n) => {
                const h = CSS.highlights.get(n);
                return h ? Array.from(h).map((r) => r.startOffset).sort((a, b) => a - b).join(',') : '';
            };
            return starts('\(name)') + '|' + starts('\(name)-current');
        })()
        """
        let raw = (try await webView.evaluateJavaScript(probe) as? String) ?? "?"
        let parts = raw.components(separatedBy: "|")
        try #require(parts.count == 2, "probe returned \(raw)")
        let ints = { (s: String) in s.split(separator: ",").compactMap { Int($0) } }
        return Lit(all: ints(parts[0]), current: ints(parts[1]))
    }

    // MARK: - A library search's hits (ReaderSearchMatchState → pageHitsScript)

    private func lightSearchHits(_ match: ReaderSearchMatchState) async throws -> Int {
        let script = DocumentKGPaneRoute.pageHitsScript(
            pageId: match.pageId, spans: match.spans, current: match.currentIndex
        )
        return ((try await webView.evaluateJavaScript(script)) as? NSNumber)?.intValue ?? -1
    }

    private static let threeCats = [
        ReaderHitSpan(start: 4, end: 7), ReaderHitSpan(start: 16, end: 19), ReaderHitSpan(start: 28, end: 31),
    ]

    /// WHY: the defect — a page with three hits showed one. All three are lit,
    /// and exactly one of them is the stronger current hit.
    @Test("N search hits on a page → N lit, exactly one current")
    func everySearchHitIsLitWithOneCurrent() async throws {
        try await load()
        let match = ReaderSearchMatchState()
        match.set(pageId: "p1", spans: Self.threeCats, current: 0)
        #expect(try await lightSearchHits(match) == 3)
        let hits = try await lit("fichero-hit")
        #expect(hits.all == [4, 16, 28], "every hit on the page is lit")
        #expect(hits.current == [4], "exactly one hit is current — the first")
    }

    /// WHY: moving the current hit must not unlight the others — the old mark
    /// path cleared the previous mark whenever a new one was drawn.
    @Test("moving the current search hit keeps the others lit")
    func movingTheCurrentSearchHitKeepsTheOthers() async throws {
        try await load()
        let match = ReaderSearchMatchState()
        match.set(pageId: "p1", spans: Self.threeCats, current: 0)
        _ = try await lightSearchHits(match)
        let before = match.signature
        match.set(pageId: "p1", spans: Self.threeCats, current: 1)
        #expect(match.signature != before, "a moved current hit re-issues the script (coordinator dedupe)")
        _ = try await lightSearchHits(match)
        let hits = try await lit("fichero-hit")
        #expect(hits.all == [4, 16, 28])
        #expect(hits.current == [16])
    }

    /// WHY: ending the search (or selecting a non-hit) must leave nothing lit —
    /// stale highlights would claim a match that is no longer the reader's.
    @Test("clearing the search unlights every hit")
    func clearingTheSearchUnlightsAll() async throws {
        try await load()
        let match = ReaderSearchMatchState()
        match.set(pageId: "p1", spans: Self.threeCats, current: 0)
        _ = try await lightSearchHits(match)
        match.clear()
        #expect(match.signature == nil)
        #expect(try await lightSearchHits(match) == 0)
        #expect(try await lit("fichero-hit") == Lit(all: [], current: []))
    }

    /// WHY: the find bar re-runs with an EMPTY query on every load and page
    /// change; if the search's hits shared its highlight they would vanish the
    /// moment the reader landed on the page.
    @Test("an empty find does not unlight the search's hits")
    func anEmptyFindLeavesSearchHitsLit() async throws {
        try await load()
        let match = ReaderSearchMatchState()
        match.set(pageId: "p1", spans: Self.threeCats, current: 0)
        _ = try await lightSearchHits(match)
        _ = try await webView.evaluateJavaScript(DocumentKGPaneRoute.findScript(query: "", activePageId: "p1"))
        #expect(try await lit("fichero-hit").all == [4, 16, 28])
    }

    /// WHY: one rule, not two — the search's hits and the find bar's matches
    /// are drawn by the same CSS rule (same colours), so they cannot drift.
    @Test("search hits and find matches share one highlight rule")
    func oneRuleForBoth() async throws {
        try await load()
        _ = try await webView.evaluateJavaScript(DocumentKGPaneRoute.findScript(query: ""))
        let probe = """
        (() => {
            const rules = Array.from(document.getElementById('fichero-find-style').sheet.cssRules)
                .map((r) => r.selectorText);
            const has = (a, b) => rules.some((s) => s.includes(a) && s.includes(b));
            return has('fichero-find)', 'fichero-hit)') && has('fichero-find-current', 'fichero-hit-current');
        })()
        """
        #expect((try await webView.evaluateJavaScript(probe) as? Bool) == true)
    }

    // MARK: - The find bar (ReaderSearchState → WebPaneFindSync)

    /// Drive the find exactly as the Reader does: `WebPaneFindSync` with
    /// `currentIndex - 1`, the count reported back into `ReaderSearchState`.
    private func syncFind(_ state: ReaderSearchState, _ sync: WebPaneFindSync) async throws {
        await withCheckedContinuation { (done: CheckedContinuation<Void, Never>) in
            sync.sync(
                into: webView, query: state.query, activePageId: "p1",
                selectionIndex: state.currentIndex - 1,
                onMatchCount: { count in state.recordMatches(count); done.resume() }
            )
        }
        sync.sync(
            into: webView, query: state.query, activePageId: "p1",
            selectionIndex: state.currentIndex - 1, onMatchCount: nil
        )
    }

    /// WHY: the find bar's N matches are all lit, one current — the behaviour
    /// the search hits now borrow, pinned so the shared rule cannot regress it.
    @Test("N find matches → N lit, exactly one current")
    func everyFindMatchIsLitWithOneCurrent() async throws {
        try await load()
        let state = ReaderSearchState()
        let sync = WebPaneFindSync()
        state.query = "cat"
        try await syncFind(state, sync)
        #expect(state.matchCount == 4, "three on p1, one on p2")
        let found = try await lit("fichero-find")
        #expect(found.all.count == 4)
        #expect(found.current == [4], "the first match on the active page is current")
    }

    /// WHY: Next moves the stronger highlight on and leaves every match lit.
    @Test("Next moves the current match without unlighting others")
    func nextMovesTheCurrentMatch() async throws {
        try await load()
        let state = ReaderSearchState()
        let sync = WebPaneFindSync()
        state.query = "cat"
        try await syncFind(state, sync)
        state.next()
        sync.sync(into: webView, query: state.query, activePageId: "p1",
                  selectionIndex: state.currentIndex - 1, onMatchCount: nil)
        let found = try await lit("fichero-find")
        #expect(found.all.count == 4)
        #expect(found.current == [16])
        #expect(state.statusText == "2 of 4")
    }

    /// WHY: dismissing the find bar must leave no match lit.
    @Test("clearing the find unlights every match")
    func clearingTheFindUnlightsAll() async throws {
        try await load()
        let state = ReaderSearchState()
        let sync = WebPaneFindSync()
        state.query = "cat"
        try await syncFind(state, sync)
        state.dismiss()
        sync.sync(into: webView, query: state.query, activePageId: "p1",
                  selectionIndex: state.currentIndex - 1, onMatchCount: nil)
        #expect(try await lit("fichero-find") == Lit(all: [], current: []))
    }

    // MARK: - Which hits are this page's

    /// WHY: the hits handed to the page come from the search result's excerpts;
    /// an excerpt anchored to ANOTHER page must not be lit at this page's offsets.
    @Test("a result's hits are the excerpts anchored to this page")
    func hitsAreThisPagesExcerpts() throws {
        let excerpt = { (page: String, start: Int) in
            """
            {"text":"cat","char_start":\(start),"char_end":\(start + 3),"match_start":\(start),"match_end":\(start + 3),
             "anchor":{"document_id":"\(page)","char_start":\(start),"char_end":\(start + 3)}}
            """
        }
        let json = """
        {"document_id":"p1","score":1,"metadata":{},
         "transcript_excerpts":[\(excerpt("p1", 4)),\(excerpt("p2", 2)),\(excerpt("p1", 16))]}
        """
        let result = try JSONDecoder().decode(SearchResult.self, from: Data(json.utf8))
        #expect(ContentView.searchHitSpans(of: result, onPage: "p1")
            == [ReaderHitSpan(start: 4, end: 7), ReaderHitSpan(start: 16, end: 19)])
    }
}
#endif
