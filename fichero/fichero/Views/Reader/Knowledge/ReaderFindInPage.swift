import Foundation
import Observation
import WebKit

// MARK: - In-reader find (#4338)

/// Per-reading-pane find state: the query, how many matches the surface
/// reported, and which match is current. Pure navigation logic so wrap-around
/// is unit-testable without a WebView.
@MainActor
@Observable
final class ReaderSearchState {
    /// The live query. Empty = find inactive (highlights cleared).
    var query = ""
    /// Matches reported by the surface for the current query.
    var matchCount = 0
    /// 1-based current match; 0 = none.
    var currentIndex = 0
    /// Whether the find bar is showing.
    var isActive = false

    /// The surface reported a fresh match count for the current query.
    func recordMatches(_ count: Int) {
        matchCount = max(0, count)
        currentIndex = matchCount > 0 ? 1 : 0
    }

    func next() { currentIndex = Self.wrapped(currentIndex + 1, count: matchCount) }
    func previous() { currentIndex = Self.wrapped(currentIndex - 1, count: matchCount) }

    func dismiss() {
        isActive = false
        query = ""
        matchCount = 0
        currentIndex = 0
    }

    /// Wrap a 1-based index into 1...count; 0 when there is nothing to select.
    static func wrapped(_ index: Int, count: Int) -> Int {
        guard count > 0 else { return 0 }
        if index < 1 { return count }
        if index > count { return 1 }
        return index
    }

    /// "2 of 14" / "No matches" / "" while inactive.
    var statusText: String {
        guard !query.isEmpty else { return "" }
        guard matchCount > 0 else { return "No matches" }
        return "\(currentIndex) of \(matchCount)"
    }
}

// MARK: - Find scripts

extension DocumentKGPaneRoute {
    /// Highlighting uses the CSS Custom Highlight API (Safari 17.2+; the app
    /// targets macOS 26/Golden Gate, so it is always present): no DOM
    /// mutation, so annotations/claim spans and the scroll-sync anchors are
    /// untouched. Defines the finder once (idempotent), then runs the query
    /// and RETURNS the match count so `evaluateJavaScript`'s completion can
    /// report it to the native find bar.
    static func findScript(query: String, activePageId: String = "") -> String {
        let literal = jsStringLiteral(query)
        let pageLiteral = jsStringLiteral(activePageId)
        return """
        (function() {
            \(findInstallScript)
            return window.__ficheroFind('\(literal)', '\(pageLiteral)');
        })();
        """
    }

    /// Select the match at `index` (0-based), marking it current and
    /// scrolling it to view. Returns the clamped index.
    static func findSelectScript(index: Int) -> String {
        "window.__ficheroFindSelect ? window.__ficheroFindSelect(\(max(0, index))) : 0;"
    }

    /// Light a library search's hits on one page (#5466): every span lit, the
    /// one at `current` stronger, through the same `__ficheroLightHits` rule
    /// the find bar uses. `pageId == nil` (or no spans) clears them. Installs
    /// the finder first, so it works whether or not the find bar ever ran, and
    /// shows the transcript tab when there is something to light. Returns how
    /// many hits were lit.
    static func pageHitsScript(pageId: String?, spans: [ReaderHitSpan], current: Int) -> String {
        let page = pageId.map { "'\(jsStringLiteral($0))'" } ?? "null"
        let list = spans.map { "[\($0.start), \($0.end)]" }.joined(separator: ", ")
        return """
        (function() {
            \(findInstallScript)
            if (\(page) != null && window.fichero && window.fichero.highlightMatchInPage) {
                window.fichero.highlightMatchInPage(\(page));
            }
            return window.__ficheroLightPageHits(\(page), [\(list)], \(current));
        })();
        """
    }

    /// The injected finder. Case-insensitive substring match over every text
    /// node in the page (matches inside a single text node — the transcript
    /// renders plain paragraphs, so that covers reading content).
    private static let findInstallScript = """
        if (!window.__ficheroFind) {
            var style = document.createElement('style');
            style.id = 'fichero-find-style';
            // ONE rule for "every hit lit, the current one stronger" (#5466):
            // the find bar's matches (`fichero-find`) and a library search's
            // anchored hits (`fichero-hit`) share these colours. Two highlight
            // NAMES only so an empty find (which clears `fichero-find`) does
            // not unlight the search's hits.
            style.textContent = '::highlight(fichero-find),::highlight(fichero-hit){background-color:rgba(255,214,10,.45);}'
                + '::highlight(fichero-find-current),::highlight(fichero-hit-current){background-color:rgba(255,149,0,.9);color:#000;}';
            (document.head || document.documentElement).appendChild(style);
            window.__ficheroFindState = { ranges: [], hits: [] };
            // The one lighting path (#5466): every range under `name`, the one
            // at `current` (0-based) also under `name-current`, scrolled to.
            // `current` < 0 lights them all with none current yet. Returns the
            // clamped current index, or -1.
            window.__ficheroLightHits = function(name, ranges, current) {
                if (!(window.CSS && CSS.highlights)) { return -1; }
                CSS.highlights.delete(name);
                CSS.highlights.delete(name + '-current');
                if (!ranges.length) { return -1; }
                CSS.highlights.set(name, new Highlight(...ranges));
                if (current < 0) { return -1; }
                var i = Math.min(current, ranges.length - 1);
                var r = ranges[i];
                CSS.highlights.set(name + '-current', new Highlight(r));
                var el = r.startContainer.parentElement;
                if (el && el.scrollIntoView) { el.scrollIntoView({ block: 'center' }); }
                return i;
            };
            // A library search's hits on one page (#5466): `spans` are
            // [start, end] PAGE-relative offsets into the page's
            // `.transcript-page-body` text (the anchor's own coordinates; a
            // span may cross a line break or an isolate, so offsets run over
            // every text node of the body). A null page clears.
            window.__ficheroLightPageHits = function(pageId, spans, current) {
                var state = window.__ficheroFindState;
                state.hits = [];
                var body = null;
                if (pageId != null) {
                    var sel = '.transcript-page[data-page-id="'
                        + ((window.CSS && CSS.escape) ? CSS.escape(pageId) : pageId) + '"]';
                    var article = document.querySelector(sel);
                    body = article ? article.querySelector('.transcript-page-body') : null;
                }
                if (body) {
                    var nodes = [];
                    var w = document.createTreeWalker(body, NodeFilter.SHOW_TEXT);
                    for (var n = w.nextNode(); n; n = w.nextNode()) { nodes.push(n); }
                    var at = function(offset, isEnd) {
                        var base = 0;
                        for (var k = 0; k < nodes.length; k++) {
                            var len = nodes[k].nodeValue.length;
                            if (offset < base + len || (isEnd && offset === base + len)) {
                                return [nodes[k], offset - base];
                            }
                            base += len;
                        }
                        return null;
                    };
                    for (var s = 0; s < spans.length; s++) {
                        var from = at(spans[s][0], false);
                        var to = at(spans[s][1], true);
                        if (!from || !to || spans[s][1] <= spans[s][0]) { continue; }
                        var r = new Range();
                        r.setStart(from[0], from[1]);
                        r.setEnd(to[0], to[1]);
                        state.hits.push(r);
                    }
                }
                window.__ficheroLightHits('fichero-hit', state.hits, current);
                return state.hits.length;
            };
            // #4406: is this element actually on screen? `checkVisibility`
            // accounts for `display:none` on any ancestor, which is exactly how
            // the inactive tabs are hidden. The `offsetParent`/`getClientRects`
            // fallback covers engines without it. FILTER_REJECT (not SKIP) on a
            // hidden element prunes its whole subtree, so a hidden tab costs one
            // check rather than a walk of everything inside it.
            window.__ficheroFindVisible = function(el) {
                if (!el) { return false; }
                if (typeof el.checkVisibility === 'function') {
                    return el.checkVisibility({ checkVisibilityCSS: true });
                }
                return !!(el.offsetParent || (el.getClientRects && el.getClientRects().length));
            };
            window.__ficheroFind = function(query, activePageId) {
                var state = window.__ficheroFindState;
                state.ranges = [];
                window.__ficheroLightHits('fichero-find', [], -1);
                if (!query || !(window.CSS && CSS.highlights)) { return 0; }
                var q = query.toLowerCase();
                // #4406: every tab's markup is RETAINED in the DOM — the
                // in-page tab bar is hidden and `fichero.showTab` drives
                // visibility — so a walk rooted at `.content` counted matches
                // in the hidden entities, claims, timeline and artifacts tabs.
                // That is how ~7 visible occurrences reported 314.
                //
                // Two independent guards, because either alone is brittle:
                // prefer the transcript container when it is the visible
                // surface, AND reject invisible nodes in the filter regardless,
                // so this survives markup changes instead of depending on one
                // selector. The filter is also what makes the count HONEST:
                // `__ficheroFindSelect` scrolls a match into view, and a range
                // in a hidden subtree cannot be scrolled to — so an unfiltered
                // count produced long runs of next/previous where nothing
                // visibly happened.
                var transcript = document.getElementById('transcript-panel')
                    || document.querySelector('.transcript');
                var root = (transcript && window.__ficheroFindVisible(transcript))
                    ? transcript
                    : (document.querySelector('.content') || document.body);
                var walker = document.createTreeWalker(
                    root,
                    NodeFilter.SHOW_TEXT,
                    {
                        acceptNode: function(candidate) {
                            return window.__ficheroFindVisible(candidate.parentElement)
                                ? NodeFilter.FILTER_ACCEPT
                                : NodeFilter.FILTER_REJECT;
                        }
                    }
                );
                var node;
                while ((node = walker.nextNode())) {
                    var text = node.nodeValue.toLowerCase();
                    var idx = 0;
                    while ((idx = text.indexOf(q, idx)) !== -1) {
                        var r = new Range();
                        r.setStart(node, idx);
                        r.setEnd(node, idx + q.length);
                        state.ranges.push(r);
                        idx += q.length;
                    }
                }
                // Take the reader to the SELECTED page's hits FIRST (Daniel,
                // 2026-09-06: "take us to the page selected first, then show
                // what's highlighted and how many"). A library-search hit lands
                // the reader on one page; a common seed term ("Marshall") also
                // occurs across the whole assembled diary, so the plain
                // document-order first match sat on some OTHER page and yanked
                // the view off the one the user picked. A STABLE partition —
                // on-page ranges first, each group keeping reading order — makes
                // the initial select (index 0) land on this page while every
                // match stays highlighted and counted. A no-op when no page is
                // active or the page holds no match, so it never disturbs the
                // plain find bar.
                if (activePageId && state.ranges.length) {
                    var onPage = [];
                    var offPage = [];
                    for (var k = 0; k < state.ranges.length; k++) {
                        var host = state.ranges[k].startContainer.parentElement;
                        var article = (host && host.closest)
                            ? host.closest('.transcript-page[data-page-id]')
                            : null;
                        if (article && article.getAttribute('data-page-id') === activePageId) {
                            onPage.push(state.ranges[k]);
                        } else {
                            offPage.push(state.ranges[k]);
                        }
                    }
                    if (onPage.length) { state.ranges = onPage.concat(offPage); }
                }
                window.__ficheroLightHits('fichero-find', state.ranges, -1);
                return state.ranges.length;
            };
            window.__ficheroFindSelect = function(index) {
                var state = window.__ficheroFindState;
                if (!state.ranges.length || !(window.CSS && CSS.highlights)) { return 0; }
                return window.__ficheroLightHits('fichero-find', state.ranges, Math.max(0, index));
            };
        }
        """
}

// MARK: - Coordinator-side sync

/// Shared find sync used by BOTH platform coordinators: re-runs the finder
/// only when the query changes, re-selects only when the current index moves,
/// and resets on a fresh document load so `didFinish` re-applies the query to
/// the new DOM. Not actor-annotated, matching the coordinators that own it —
/// WebKit invokes everything here on the main thread.
final class WebPaneFindSync {
    private var lastQuery: String?
    private var lastActivePageId: String?
    private var lastIndex = -1

    func reset() {
        lastQuery = nil
        lastActivePageId = nil
        lastIndex = -1
    }

    func sync(
        into webView: WKWebView,
        query: String,
        activePageId: String,
        selectionIndex: Int,
        onMatchCount: (@MainActor @Sendable (Int) -> Void)?
    ) {
        // Re-run when the query OR the active page changes: the same query on a
        // new page must re-partition so the initial select lands on THAT page.
        if lastQuery != query || lastActivePageId != activePageId {
            lastQuery = query
            lastActivePageId = activePageId
            lastIndex = -1
            // WKWebView is main-actor; this class is called on the main
            // thread (see the class doc) but is not actor-annotated, so
            // assert the isolation rather than restating it on every owner.
            MainActor.assumeIsolated {
                webView.evaluateJavaScript(DocumentKGPaneRoute.findScript(query: query, activePageId: activePageId)) { result, _ in
                    let count = (result as? NSNumber)?.intValue ?? 0
                    // WebKit calls this completion on the main thread; hop
                    // explicitly so the isolation is checked, not assumed.
                    Task { @MainActor in onMatchCount?(count) }
                }
            }
        }
        if !query.isEmpty, selectionIndex >= 0, lastIndex != selectionIndex {
            lastIndex = selectionIndex
            MainActor.assumeIsolated {
                webView.evaluateJavaScript(DocumentKGPaneRoute.findSelectScript(index: selectionIndex))
            }
        }
    }
}
