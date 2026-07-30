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
