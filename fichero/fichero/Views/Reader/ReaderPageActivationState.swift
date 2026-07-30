import Foundation
import Observation
import OSLog

/// Shared by both platform coordinators, which live in separate files but
/// report the same malformed-payload condition.
let readerPageActivationLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "ReaderPageActivation"
)

/// A page the user ASKED for by clicking it in the reader (#4373).
///
/// Deliberately distinct from the scroll-sync page report. Scrolling past a
/// page is the viewport drifting; clicking one is an instruction. #1463 made
/// scroll-sync update only the page-focus cursor, never the browser selection
/// or the previewed document — correct, because a scroll must not re-root what
/// the window is looking at. A click must, which is why it needs its own
/// message rather than a flag on the old one.
struct ReaderPageActivation: Equatable {
    /// The page number as the transcript labels it, 1-based.
    let pageNumber: Int

    /// 0-based index into the parent's ordered page children — the form the
    /// existing `pageDocument(atPDFIndex:in:)` resolver takes.
    var pageIndex: Int { pageNumber - 1 }
}

/// What a reader page signal is ALLOWED to move (#4373 over #1463).
///
/// The two signals resolve to the same page document and differ only in how
/// much of the window they may re-point. Stating that as a value rather than
/// as two hand-written branches is what makes the #1463 invariant assertable:
/// a scroll must never re-root the window, and NEITHER may re-root the
/// previewed document, because that document is the reader's own input and
/// changing it reloads the transcript out from under the reader.
enum ReaderPageSignal: Equatable {
    /// The viewport drifted past this page while scrolling.
    case scrolledPast
    /// The user clicked this page. An instruction, not a side effect.
    case clicked

    /// Both move the page-focus cursor — that is what drives the preview's
    /// page and the inspector (#1463).
    var movesPageFocus: Bool { true }

    /// Only a click moves the library/sidebar selection. Scrolling a long
    /// transcript would otherwise drag the browser selection along behind it.
    var movesBrowserSelection: Bool { self == .clicked }

    /// NEITHER re-roots `detailDocument`. It stays pinned to the container
    /// (the parent PDF / folder) so the WebKit transcript is not torn down and
    /// reloaded by the very click that was meant to move within it.
    var rerootsPreviewedDocument: Bool { false }
}

/// Keeping the transcript's own "this page is selected" border honest (#4373).
///
/// The border is not new and neither is its CSS: the engine template already
/// has `.transcript-page.current { border-color: var(--accent) }` and a
/// `setActivePage(_)` bridge function, driven from Swift with
/// `DocumentKGWebPane.activePageNumber` — which is `selectedPageIndex + 1`,
/// which is `pdfPageIndex(for: pageFocusDocument ?? detailDocument)`. So the
/// border ALREADY reads from the page-focus cursor, which is what both
/// `ReaderPageSignal` cases move. By construction it cannot disagree with the
/// click, and there is no second addressing scheme to introduce.
///
/// What was broken is the DRIVE. The old sync recorded the value as sent
/// *before* two early returns:
///
///     if lastActivePageNumber != parent.activePageNumber {
///         lastActivePageNumber = parent.activePageNumber   // recorded…
///         if Date() < suppressActivePageSyncUntil { return }  // …but not sent
///         if parent.scrollSync.isDriving(.web) { return }     // …but not sent
///
/// so any cursor move landing inside the 0.25s suppression window — which is
/// exactly the window a click following a scroll lands in — was marked
/// delivered and never drawn. The next tick then saw "no change" and skipped.
/// The border stayed on the wrong page until the cursor happened to move
/// again: the reader lying about which page is selected, which is the same
/// defect class as the connection surfaces disagreeing in #4380.
///
/// The fix splits the two things that suppression was conflating. The
/// HIGHLIGHT is never suppressed — a border that is not current is worse than
/// no border. The SCROLL is, because when the web view itself drove the change
/// (a scroll, or a click on a page already on screen) the user is looking at
/// the page already and yanking it to `block: 'start'` moves the content out
/// from under them.
enum ReaderActivePageSync {
    struct Decision: Equatable {
        /// Move the border. True whenever the cursor differs from what was
        /// last drawn, under every suppression condition.
        let sendsHighlight: Bool
        /// Also scroll the transcript to that page.
        let sendsScroll: Bool

        /// The caller may record the value as delivered ONLY when the
        /// highlight actually went out. Recording an unsent value is the
        /// staleness bug, so the two are tied together here rather than left
        /// to each call site to remember.
        var recordsAsSent: Bool { sendsHighlight }
    }

    static func decide(
        lastSent: Int?,
        desired: Int?,
        isScrollSuppressed: Bool,
        isWebDriving: Bool
    ) -> Decision {
        // Already drawn where it belongs — including the repeated-click case,
        // where the cursor did not move because the page was already current.
        guard lastSent != desired else {
            return Decision(sendsHighlight: false, sendsScroll: false)
        }
        return Decision(
            sendsHighlight: true,
            // A nil cursor clears the border and has nowhere to scroll to.
            sendsScroll: desired != nil && !isScrollSuppressed && !isWebDriving
        )
    }

    /// `null` clears it — the engine's `applyActivePageHighlight` treats a null
    /// `activePage` as "no page current" and drops the class from every page,
    /// so a cursor that becomes nil removes the border instead of stranding it.
    static func highlightScript(page: Int?) -> String {
        let argument: String
        if let page {
            argument = "\(page)"
        } else {
            argument = "null"
        }
        return "window.fichero?.setActivePage(\(argument));"
    }

    static func scrollScript(page: Int, pageCount: Int) -> String {
        "window.ficheroScrollToPage?.(\(page), \(pageCount));"
    }
}

/// Per-window bus for reader page activations (#4373).
///
/// Scoped to the window's subtree via the SwiftUI environment, never `.shared`,
/// matching `ClaimSourceNavigationState` and the #3437 scoping invariant: two
/// windows reading two documents must not steer each other.
///
/// `requestID` is what observers watch. It advances on every activation even
/// when the SAME page is clicked twice, because clicking the already-current
/// page is still a request to select it — the second click must not be
/// swallowed as "no change".
@Observable
@MainActor
final class ReaderPageActivationState {
    private(set) var requestID: Int = 0
    private(set) var currentRequest: ReaderPageActivation?

    /// Record a click on `pageNumber`. Page numbers are 1-based; anything else
    /// is a malformed bridge payload and is rejected rather than silently
    /// clamped to page 1 — substituting a different page is exactly the kind
    /// of quiet wrong answer that makes a navigation bug unfindable.
    func activate(pageNumber: Int) -> Bool {
        guard pageNumber >= 1 else { return false }
        currentRequest = ReaderPageActivation(pageNumber: pageNumber)
        requestID &+= 1
        return true
    }
}
