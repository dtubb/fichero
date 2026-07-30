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
    static func findScript(query: String) -> String {
        let literal = jsStringLiteral(query)
        return """
        (function() {
            \(findInstallScript)
            return window.__ficheroFind('\(literal)');
        })();
        """
    }

    /// Select the match at `index` (0-based), marking it current and
    /// scrolling it to view. Returns the clamped index.
    static func findSelectScript(index: Int) -> String {
        "window.__ficheroFindSelect ? window.__ficheroFindSelect(\(max(0, index))) : 0;"
    }

    /// The injected finder. Case-insensitive substring match over every text
    /// node in the page (matches inside a single text node — the transcript
    /// renders plain paragraphs, so that covers reading content).
    private static let findInstallScript = """
        if (!window.__ficheroFind) {
            var style = document.createElement('style');
            style.id = 'fichero-find-style';
            style.textContent = '::highlight(fichero-find){background-color:rgba(255,214,10,.45);}'
                + '::highlight(fichero-find-current){background-color:rgba(255,149,0,.9);color:#000;}';
            (document.head || document.documentElement).appendChild(style);
            window.__ficheroFindState = { ranges: [] };
            window.__ficheroFind = function(query) {
                var state = window.__ficheroFindState;
                state.ranges = [];
                if (window.CSS && CSS.highlights) {
                    CSS.highlights.delete('fichero-find');
                    CSS.highlights.delete('fichero-find-current');
                }
                if (!query || !(window.CSS && CSS.highlights)) { return 0; }
                var q = query.toLowerCase();
                var root = document.querySelector('.content') || document.body;
                var walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
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
                if (state.ranges.length) {
                    CSS.highlights.set('fichero-find', new Highlight(...state.ranges));
                }
                return state.ranges.length;
            };
            window.__ficheroFindSelect = function(index) {
                var state = window.__ficheroFindState;
                if (!state.ranges.length || !(window.CSS && CSS.highlights)) { return 0; }
                var i = Math.max(0, Math.min(index, state.ranges.length - 1));
                var r = state.ranges[i];
                CSS.highlights.set('fichero-find-current', new Highlight(r));
                var el = r.startContainer.parentElement;
                if (el && el.scrollIntoView) { el.scrollIntoView({ block: 'center' }); }
                return i;
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
    private var lastIndex = -1

    func reset() {
        lastQuery = nil
        lastIndex = -1
    }

    func sync(
        into webView: WKWebView,
        query: String,
        selectionIndex: Int,
        onMatchCount: ((Int) -> Void)?
    ) {
        if lastQuery != query {
            lastQuery = query
            lastIndex = -1
            webView.evaluateJavaScript(DocumentKGPaneRoute.findScript(query: query)) { result, _ in
                let count = (result as? NSNumber)?.intValue ?? 0
                onMatchCount?(count)
            }
        }
        if !query.isEmpty, selectionIndex >= 0, lastIndex != selectionIndex {
            lastIndex = selectionIndex
            webView.evaluateJavaScript(DocumentKGPaneRoute.findSelectScript(index: selectionIndex))
        }
    }
}
