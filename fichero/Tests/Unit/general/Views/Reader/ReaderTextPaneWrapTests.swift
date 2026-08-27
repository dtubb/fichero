#if canImport(AppKit)
import AppKit
@testable import Fichero
import Testing

/// The Reader's OTHER text surface must wrap too (#4385).
///
/// ## Why this file exists separately
///
/// The issue says the transcript "renders in WebKit", and the Transcript tab
/// does. But the Reader shows document text through a second, unrelated
/// surface: `AnnotatableTextView`, an AppKit `NSTextView` bridge, used by
/// `PageContentPane` (the selected PDF page's transcription) and by
/// `DocumentTextReader` (whole-document txt / docx / md). It shares no code
/// and no styling with the WebKit pane.
///
/// Fixing the CSS and stopping there would have left that surface unchecked
/// while the issue read as closed — the "fix one instance, miss the class"
/// shape. It was checked, it does wrap, and this is what keeps it that way.
///
/// ## What is actually measured
///
/// `NSLayoutManager.usedRect(for:)` is the width the laid-out text really
/// occupies. Comparing it to the text view's own width, and the text view's
/// width to the visible clip width, is the AppKit spelling of
/// "scrollWidth <= clientWidth": content no wider than its box, box no wider
/// than the pane. Asserting on the configuration flags alone would not catch a
/// future change that keeps the flags and breaks the layout.
@MainActor
struct ReaderTextPaneWrapTests {

    /// One OCR line with no break opportunity anywhere in it — the same input
    /// the WebKit transcript test uses, because it is the same corpus.
    private static let unbreakableOCRLine = String(repeating: "8", count: 4000)

    private struct Laid {
        let usedWidth: CGFloat
        let textViewWidth: CGFloat
        let visibleWidth: CGFloat

        /// The text is wider than the view drawing it.
        var textOverflowsItsView: Bool { usedWidth > textViewWidth + 0.5 }
        /// The view is wider than the pane, i.e. the pane scrolls sideways.
        var viewOverflowsThePane: Bool { textViewWidth > visibleWidth + 0.5 }

        var description: String {
            "used \(Int(usedWidth)) / view \(Int(textViewWidth)) / visible \(Int(visibleWidth))"
        }
    }

    /// Lay `text` out at `width` points and report what it occupied.
    private static func layOut(
        _ text: String,
        width: CGFloat,
        configure: (NSTextView) -> Void = { _ in }
    ) -> Laid {
        let (scrollView, textView) = AnnotatableTextView.makeWrappingTextScrollView()
        configure(textView)
        scrollView.frame = NSRect(x: 0, y: 0, width: width, height: 480)
        textView.string = text
        scrollView.layoutSubtreeIfNeeded()

        guard let container = textView.textContainer, let manager = textView.layoutManager else {
            return Laid(usedWidth: .infinity, textViewWidth: 0, visibleWidth: 0)
        }
        manager.ensureLayout(for: container)
        return Laid(
            usedWidth: manager.usedRect(for: container).width,
            textViewWidth: textView.frame.width,
            visibleWidth: scrollView.contentView.bounds.width
        )
    }

    // MARK: - The contract

    @Test("a 4000-character unbroken OCR line does not widen the page pane")
    func unbreakableLineDoesNotWidenThePagePane() {
        let laid = Self.layOut(Self.unbreakableOCRLine, width: 200)

        #expect(!laid.textOverflowsItsView, Comment(rawValue: laid.description))
        #expect(!laid.viewOverflowsThePane, Comment(rawValue: laid.description))
    }

    /// "At every pane size, including very narrow." The reader is one of three
    /// panes and gets narrowed to make room for the library; that is the case
    /// where wrapping matters most, so it is the case most worth pinning.
    @Test("it holds at every pane width, not just the one that was checked")
    func itHoldsAtEveryPaneWidth() {
        let mixed = Self.unbreakableOCRLine + "\n" + String(repeating: "palabra ", count: 300)
        for width in [120.0, 200.0, 400.0, 900.0] as [CGFloat] {
            let laid = Self.layOut(mixed, width: width)
            let detail = "at \(Int(width))pt — \(laid.description)"
            #expect(!laid.textOverflowsItsView, Comment(rawValue: detail))
            #expect(!laid.viewOverflowsThePane, Comment(rawValue: detail))
        }
    }

    /// The pane has one scroll axis. A horizontal scroller is not the defect
    /// itself — the overflow is — but shipping one advertises the defect.
    @Test("the pane offers no horizontal scroller")
    func thePaneOffersNoHorizontalScroller() {
        let (scrollView, _) = AnnotatableTextView.makeWrappingTextScrollView()

        #expect(!scrollView.hasHorizontalScroller)
        #expect(scrollView.hasVerticalScroller)
    }

    /// **The negative control.**
    ///
    /// The assertions above are all "nothing overflows", and those pass for
    /// free if the text never laid out, the container was nil, or the
    /// measurement is reading the wrong number. This configures the text view
    /// the way an unwrapped reader is configured — free to grow horizontally,
    /// with a container that ignores the view's width — and requires the same
    /// measurement to catch it.
    ///
    /// Without this, "no overflow detected" and "no measurement happened" are
    /// the same green.
    @Test("the same measurement catches an unwrapped text view")
    func theMeasurementCatchesAnUnwrappedTextView() {
        let laid = Self.layOut(Self.unbreakableOCRLine, width: 200) { textView in
            textView.isHorizontallyResizable = true
            textView.textContainer?.widthTracksTextView = false
            textView.textContainer?.size = NSSize(
                width: CGFloat.greatestFiniteMagnitude,
                height: CGFloat.greatestFiniteMagnitude
            )
        }

        #expect(
            laid.textOverflowsItsView,
            Comment(rawValue: """
            an unwrapped text view did NOT register as overflowing \
            (\(laid.description)) — this measurement cannot detect the bug it \
            exists to detect, so the passing tests above prove nothing
            """)
        )
    }
}
#endif
