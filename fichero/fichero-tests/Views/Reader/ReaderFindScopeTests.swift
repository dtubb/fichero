@testable import Fichero
import Foundation
import Testing

/// #4406: reader Find reported 314 matches for roughly 7 visible occurrences.
///
/// Every tab's markup is RETAINED in the DOM — the in-page tab bar is hidden
/// and `fichero.showTab` drives visibility (`document_view.html`) — so a walk
/// rooted at `.content` counted matches inside the hidden entities, claims,
/// timeline and artifacts tabs.
///
/// The second-order effect is what makes it worse than a wrong number:
/// `__ficheroFindSelect` scrolls the selected range into view, and a range in
/// a `display:none` subtree cannot be scrolled to. So next/previous walked
/// long runs where nothing visibly happened — the count was not merely
/// inflated, it was unusable.
///
/// These assert the injected script's shape. The script is a string in Swift,
/// so this is the level at which it can be held without a browser; the
/// behavioural half needs a build.
struct ReaderFindScopeTests {
    private static func appSource(_ relativePath: String) throws -> String {
        let url = URL(fileURLWithPath: #filePath)
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .deletingLastPathComponent()
            .appendingPathComponent("fichero")
            .appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    private static var findSource: String {
        get throws { try appSource("Views/Reader/Knowledge/ReaderFindInPage.swift") }
    }

    /// The walk must reject invisible nodes. This is the guard that survives
    /// markup changes — it does not care which selector hides what.
    @Test("the text walk rejects invisible nodes")
    func theWalkRejectsInvisibleNodes() throws {
        let source = try Self.findSource
        #expect(source.contains("acceptNode"))
        #expect(source.contains("NodeFilter.FILTER_REJECT"))
        #expect(source.contains("window.__ficheroFindVisible"))
        // REJECT, not SKIP: skipping a hidden tab would still walk everything
        // inside it.
        #expect(!source.contains("NodeFilter.FILTER_SKIP"))
    }

    /// A bare `createTreeWalker(root, NodeFilter.SHOW_TEXT)` with no filter is
    /// the original bug. It must not come back.
    @Test("no unfiltered tree walk remains")
    func noUnfilteredWalkRemains() throws {
        let source = try Self.findSource
        #expect(!source.contains("createTreeWalker(root, NodeFilter.SHOW_TEXT);"))
    }

    /// Prefer the reading surface as the root when it is the visible one —
    /// belt to the filter's braces, and it keeps the common case cheap.
    @Test("the walk prefers the transcript container when it is visible")
    func theWalkPrefersTheTranscript() throws {
        let source = try Self.findSource
        #expect(source.contains("transcript-panel"))
        #expect(source.contains("window.__ficheroFindVisible(transcript)"))
        // …but still falls back, so a different visible tab is searchable
        // rather than reporting zero.
        #expect(source.contains("document.querySelector('.content') || document.body"))
    }

    /// `checkVisibility` accounts for `display:none` on any ANCESTOR, which is
    /// exactly how the inactive tabs are hidden — an inline-style check on the
    /// node itself would miss them.
    @Test("visibility is tested through ancestors, with a fallback")
    func visibilityIsTestedThroughAncestors() throws {
        let source = try Self.findSource
        #expect(source.contains("checkVisibility"))
        #expect(source.contains("checkVisibilityCSS"))
        #expect(source.contains("offsetParent"))
    }

    /// The invariant that ties the count to the interaction: every counted
    /// match must be selectable AND scrollable into view. The filter is what
    /// guarantees it — a range only enters `state.ranges` if its parent passed
    /// the visibility test, and `__ficheroFindSelect` scrolls that same parent.
    @Test("every counted match is one the selector can scroll to")
    func everyCountedMatchIsScrollable() throws {
        let source = try Self.findSource
        // Ranges are only pushed inside the filtered walk…
        #expect(source.contains("state.ranges.push(r)"))
        // …and the selector scrolls the parent of a range's start container,
        // which the filter has already proven visible.
        #expect(source.contains("r.startContainer.parentElement"))
        #expect(source.contains("scrollIntoView"))
    }

    /// The highlighting approach is deliberately unchanged — only the scope of
    /// the walk was wrong.
    @Test("the CSS Custom Highlight approach is unchanged")
    func highlightApproachIsUnchanged() throws {
        let source = try Self.findSource
        #expect(source.contains("CSS.highlights"))
        #expect(source.contains("new Highlight("))
        #expect(source.contains("::highlight(fichero-find)"))
    }
}
