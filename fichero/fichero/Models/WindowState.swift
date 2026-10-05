import Observation
import SwiftUI

/// Tracks the state for a single window
/// Each window views one library and can have multiple tabs
@MainActor
@Observable
class WindowState {
    /// ID of the library this window is viewing
    var libraryId: UUID

    /// Currently selected tab
    var selectedTab: String = "library"

    /// A document THIS window should focus once its rows load — the per-window
    /// half of the "Open in New Tab/Window" hand-off (#1685). Claimed from the
    /// shared `LibraryManager.pendingOpenDocumentId` by `initializeWindow` when
    /// this freshly opened window takes its library, so a BACKGROUND window
    /// sharing the same library's `documentStore` can no longer consume the
    /// intent on a revision tick and hijack the open into the wrong window.
    var pendingOpenDocumentId: String?

    /// The document selection a workflow run must honor (#4523 LAW: "a
    /// workflow's scope is the CURRENT SELECTION at gesture time; selection
    /// means the selected items, not their peers").
    ///
    /// Written by ContentView whenever the library-pane selection becomes
    /// non-empty, and — deliberately — NOT cleared by sidebar navigation:
    /// the #712 policy clears `browserSelection` the moment the user
    /// navigates (for example to a workflow node, in order to run it), which
    /// is exactly the moment the selection must be remembered. It IS cleared
    /// when the user selects a different library container (the browse
    /// context moved on, so a remembered selection would be stale scope).
    /// Every run surface reads its effective selection through this.
    var preservedDocumentSelection: [String] = []

    /// The LIVE library-pane selection, mirrored from `browserSelection` on
    /// every change — INCLUDING to empty. A sidebar row's context-menu run
    /// reads THIS, never the preserved snapshot: the snapshot can be
    /// arbitrarily old, and a stale multi-selection that happened to contain
    /// the clicked file expanded a one-file run onto every sibling
    /// (Daniel, 2026-08-15). Preservation keeps serving the workflow-editor
    /// surface it was built for (#4523); the live mirror serves surfaces
    /// where the user is pointing at a specific row RIGHT NOW.
    var liveDocumentSelection: [String] = []

    /// Why the last drop onto a library folder cell failed, or nil (#4474).
    /// Rendered by `LibraryView`'s drop alert. The sidebar has the same surface
    /// in `SidebarState.dropErrorMessage`; the library pane had none at all, so
    /// a failed cell drop was logged and otherwise looked exactly like a drop
    /// that had worked.
    var dropErrorMessage: String?

    /// Monotonic request token for "open the workflow picker over the current
    /// selection" (the island's ⚡ chip). A counter, not a Bool: LibraryView
    /// reacts to the CHANGE, so pressing the chip again after dismissing the
    /// picker fires again. Direct @Observable seam per §6b — never a
    /// NotificationCenter post.
    var workflowPickerRequestToken = 0

    /// A contextual suggestion button was pressed (2026-08-25): run THIS
    /// default workflow (by canonical name — ids are per-library) over the
    /// current selection. Token-stamped so the same button fires twice.
    struct SuggestedWorkflowRequest: Equatable {
        let workflowName: String
        let token: Int
    }
    var suggestedWorkflowRequest: SuggestedWorkflowRequest?

    /// Ephemeral rubber-band selections drawn over this window's Preview
    /// image (Daniel, 2026-08-29). Lives HERE so it is per-window by
    /// construction — the workflow bar reads it as a run scope, and two
    /// windows' marquees must never mix. See `PreviewMarqueeSelection`.
    let previewMarquees = PreviewMarqueeSelection()

    /// The annotation bar's ARMED tool (Daniel, 2026-08-30: "when we change
    /// tools for markup… leave it selected"). Sticky: the tool stays armed
    /// across uses until toggled off or another tool is armed; canvases read
    /// it for behaviour and cursor. Per-window, like the marquee seam.
    /// Select is ON from the first click (Daniel, 2026-09-02: "Selection
    /// should default on") — a window opens able to select regions without
    /// first opening the markup bar.
    var activeMarkupTool: PreviewMarkupTool? = .select

    /// Segment editing is a MODE of the Source view (`source.editor.segment-focus`, #5114,
    /// ruled 2026-09-27). Off -- the default -- the page is for reading and nothing on it
    /// changes; `SegmentEditingMode` holds the rule. Per-window, like the armed tool: two
    /// Source views split in one window edit together.
    var isEditingSegments = false

    /// What the Segments pane shows instead of the page: a set gathered from the Inspector --
    /// "Everything in This Hand", "Every Instance" of a sign (#4942). Nil shows the page.
    var segmentsGather: SegmentsGather?

    /// What the one Shape tool draws in Edit Segments (`source.editor.draw-shapes`): a dragged box, or a
    /// polygon or baseline clicked point by point. Outside Edit Segments the tool always drags a box.
    var shapeKind: SegmentShapes.DrawKind = .box

    /// The shape point last pressed in Edit Segments: the arrow keys nudge it (1 px, ⇧ 10) instead of
    /// paging. A press anywhere else lets it go.
    var selectedShapePoint: SegmentShapes.PointRef?

    /// The points of a polygon or baseline being drawn with the Shape tool, in the order clicked. Here,
    /// not in the canvas layer, so Escape (the preview's exit command) can abandon it.
    var drawingPoints: [[Double]] = []

    /// Escape during a drawing: drop the points clicked so far and make nothing. True when there was a
    /// drawing to abandon -- that Escape does nothing else; the next one clears as it always has.
    @discardableResult
    func abandonDrawing() -> Bool {
        guard !drawingPoints.isEmpty else { return false }
        drawingPoints = []
        return true
    }

    /// A segment to select once its page is shown: Next in a flow crossing onto another page (#5160).
    /// The Order list on that page takes it and clears it.
    var pendingSegmentSelection: ReadingOrderChoice.Landing?

    /// The FOCUSED Source-view pane's region selection (#5020, ruled 2026-09-27): each pane owns
    /// its own, and the Inspector and the markup row act on this one. Strong, not weak (an
    /// `@Observable` property), so the pane releases it when it goes (`releaseRegionSelection`).
    private(set) var focusedRegionSelection: RegionSelection?

    /// A pane was USED (a click, a band, ⌘A, a verb): its selection is the one the window acts on.
    func focusRegionSelection(_ selection: RegionSelection) {
        if focusedRegionSelection !== selection { focusedRegionSelection = selection }
    }

    /// Reveal segments in the linked Preview -- the focused Source-view pane (#5424): its box selected,
    /// scrolled and zoomed to, through the one `InspectorPath.reveal`. The Order tab, the Order pane and
    /// the Reader all call this. Answers the ids selected; none when no Preview is focused.
    @discardableResult
    func revealSegments(_ segmentIds: [String], documentId: String, store: SegmentStore) -> [String] {
        guard let focusedRegionSelection else { return [] }
        return InspectorPath.reveal(
            segmentIds: segmentIds, into: focusedRegionSelection, documentId: documentId, store: store
        )
    }

    /// A pane appeared: it becomes the focus only if nothing is focused yet, so opening a second
    /// Preview does not steal the Inspector from the one a person is working in.
    func offerRegionSelection(_ selection: RegionSelection) {
        if focusedRegionSelection == nil { focusedRegionSelection = selection }
    }

    /// A pane went away: drop the focus only if it was that pane's.
    func releaseRegionSelection(_ selection: RegionSelection) {
        if focusedRegionSelection === selection { focusedRegionSelection = nil }
    }

    /// Coding v1 (Daniel, 2026-08-30, ruling 4): comma-separated tags entered
    /// via the highlight menu's "Tag Next Highlight…" ride the NEXT saved
    /// highlight / underline / strikethrough / check, then clear — one-shot,
    /// per-window like the armed tool. Canvases consume via
    /// `takePendingMarkupTags()` at the save site.
    var pendingMarkupTags: [String] = []

    /// One-shot read of `pendingMarkupTags`: returns them and clears, so a
    /// multi-strip save (word-snapped highlight) tags every strip of ONE
    /// gesture but never the next gesture.
    func takePendingMarkupTags() -> [String] {
        let tags = pendingMarkupTags
        pendingMarkupTags = []
        return tags
    }

    /// A quiet, transient reason shown over the preview canvas when a markup
    /// gesture is refused (Daniel, 2026-09-04: a drag over box-less canvas
    /// "refuses with a quiet reason rather than minting an unanchored mark").
    /// Honest refusal, not silence — and not a modal.
    var markupNotice: String?
    private var markupNoticeToken = 0

    /// Show `reason` over the canvas for a few seconds, then clear — unless a
    /// newer notice has replaced it in the meantime.
    func showMarkupNotice(_ reason: String) {
        markupNoticeToken += 1
        let token = markupNoticeToken
        markupNotice = reason
        Task { @MainActor [weak self] in
            try? await Task.sleep(for: .seconds(2.5))
            guard let self, self.markupNoticeToken == token else { return }
            self.markupNotice = nil
        }
    }

    // MARK: - UI verbs (#5453, `openapi.ui.verbs-are-the-click`)

    /// The window a UI verb (AppleScript, App Intent) acts on: the last one made key on the Mac, the
    /// one scene's on iPhone and iPad. Weak, so a closed window is never driven.
    static weak var front: WindowState?

    /// What a UI verb asked THIS window for; `ContentView.applyUIVerb` does it through the click's own
    /// method. A token, so asking twice acts twice.
    var uiVerbRequest: UIVerbRequest?

    /// Ask this window for what a click does (`UIVerbs` is the only caller).
    func request(_ action: UIVerbRequest.Action) {
        uiVerbRequest = UIVerbRequest(action: action, token: (uiVerbRequest?.token ?? 0) + 1)
    }

    /// Where each shown pane sits in the window (window points, top-left origin), by pane name, for
    /// the screenshot verb. Not observed: nothing draws from it.
    @ObservationIgnored var paneFrames: [String: CGRect] = [:]

    #if os(macOS)
    /// The window this state draws in; becoming key makes this state the `front` one.
    @ObservationIgnored weak var hostWindow: NSWindow? {
        didSet {
            guard hostWindow !== oldValue else { return }
            if let keyObserver { NotificationCenter.default.removeObserver(keyObserver) }
            keyObserver = nil
            guard let hostWindow else { return }
            if hostWindow.isKeyWindow || Self.front == nil { Self.front = self }
            keyObserver = NotificationCenter.default.addObserver(
                forName: NSWindow.didBecomeKeyNotification, object: hostWindow, queue: .main
            ) { [weak self] _ in
                MainActor.assumeIsolated { WindowState.front = self }
            }
        }
    }
    @ObservationIgnored private var keyObserver: (any NSObjectProtocol)?
    #endif

    init(libraryId: UUID) {
        self.libraryId = libraryId
    }

    /// Get the library reference from LibraryManager
    var library: LibraryManager.LibraryReference? {
        LibraryManager.shared.getLibrary(id: libraryId)
    }

    /// Get the APIClient for this window's library
    var apiClient: APIClient? {
        library?.apiClient
    }

    /// Get the document for this window's library
    var document: FicheroDocument? {
        library?.document
    }
}
