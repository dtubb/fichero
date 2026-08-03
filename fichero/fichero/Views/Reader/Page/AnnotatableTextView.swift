#if canImport(AppKit)
import AppKit
import SwiftUI

/// Read-only, selectable text that renders saved annotation highlights and
/// reports the user's selection as a UTF-16 range (#2458).
///
/// SwiftUI `Text` exposes neither the selected range nor per-range backgrounds,
/// so this is an isolated AppKit bridge — the sanctioned reason to drop to
/// `NSViewRepresentable`. Highlights are drawn as background colour over the
/// stored char spans; the selection binding drives the annotation toolbar.
struct AnnotatableTextView: NSViewRepresentable {
    let text: String
    var highlights: [Range<Int>]
    @Binding var selection: Range<Int>?
    /// Reader text font scale (#3681) — this is a Reader surface. A change
    /// re-invokes `updateNSView`, which re-applies the scaled font in place.
    @AppStorage(ViewSettings.FontScale.readerKey)
    private var readerScale = ViewSettings.FontScale.defaultValue

    /// The serif reading font at the semantic `.body` base size × the Reader
    /// scale — scales the semantic base, never a hardcoded size.
    private static func serifBodyFont(scale: Double) -> NSFont {
        let base = NSFont.preferredFont(forTextStyle: .body)
        let size = base.pointSize * scale
        return base.fontDescriptor.withDesign(.serif)
            .flatMap { NSFont(descriptor: $0, size: size) } ?? base
    }

    private var scaledFont: NSFont {
        Self.serifBodyFont(scale: ViewSettings.FontScale.clamped(readerScale))
    }

    func makeCoordinator() -> Coordinator { Coordinator(selection: $selection) }

    /// Build the reader's scroll view + text view, configured so the text
    /// WRAPS to the pane and the pane has exactly one scroll axis (#4385).
    ///
    /// Factored out of `makeNSView` so the wrap contract can be measured
    /// directly. `NSViewRepresentable.Context` cannot be constructed in a test,
    /// so as long as this configuration lived inside `makeNSView` the only
    /// thing a test could check was that the source file contained the right
    /// words — which is not the same as the text actually wrapping. The reader
    /// is where the historian works, and an OCR page that arrives as one
    /// 4000-character line is the normal case on a handwriting corpus, not an
    /// edge case, so the contract is worth measuring rather than asserting.
    ///
    /// The three properties that make it hold, and why each is load-bearing:
    ///
    /// - `hasHorizontalScroller = false` hides the scroller but does NOT stop
    ///   the overflow, so it is the weakest of the three and cannot be the only
    ///   one. The issue is explicit that a hidden scrollbar over a still-wide
    ///   document is not a fix.
    /// - `isHorizontallyResizable = false` is what makes the scroll view size
    ///   the text view to the visible width instead of letting it grow to its
    ///   content. It is also the default for a programmatically created
    ///   `NSTextView`, which is exactly why it is set explicitly here: an
    ///   invariant that survives only because nobody has typed the opposite is
    ///   not an invariant.
    /// - `widthTracksTextView = true` passes that width down to the text
    ///   container, which is what the layout manager actually wraps against.
    @MainActor
    static func makeWrappingTextScrollView() -> (scrollView: NSScrollView, textView: NSTextView) {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder

        let textView = NSTextView()
        textView.isEditable = false
        textView.isSelectable = true
        textView.drawsBackground = false
        textView.textContainerInset = NSSize(width: 8, height: 8)
        textView.isHorizontallyResizable = false
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.lineFragmentPadding = 0

        scrollView.documentView = textView
        return (scrollView, textView)
    }

    func makeNSView(context: Context) -> NSScrollView {
        let (scrollView, textView) = Self.makeWrappingTextScrollView()
        textView.delegate = context.coordinator
        context.coordinator.textView = textView
        context.coordinator.apply(text: text, highlights: highlights, font: scaledFont)
        return scrollView
    }

    func updateNSView(_ nsView: NSScrollView, context: Context) {
        context.coordinator.apply(text: text, highlights: highlights, font: scaledFont)
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        private let selection: Binding<Range<Int>?>
        weak var textView: NSTextView?
        private var lastText: String?
        private var lastHighlights: [Range<Int>] = []
        private var lastFontPointSize: CGFloat = 0

        init(selection: Binding<Range<Int>?>) { self.selection = selection }

        /// Sync content + highlight backgrounds. Cheap-guards on unchanged text,
        /// font size, and highlights so typing/scrolling doesn't rebuild
        /// attributes — but a Reader font-scale change (font size) does (#3681).
        /// `@MainActor`: touches main-actor `NSTextView.textStorage`/`.string`;
        /// every caller (`makeNSView`/`updateNSView`) already runs on the main
        /// actor, so this only makes the existing isolation explicit (#3977).
        @MainActor
        func apply(text: String, highlights: [Range<Int>], font: NSFont) {
            guard let textView, let storage = textView.textStorage else { return }
            let textChanged = lastText != text
            if textChanged {
                textView.string = text
                lastText = text
            }
            let fontChanged = font.pointSize != lastFontPointSize
            guard textChanged || fontChanged || highlights != lastHighlights else { return }
            lastFontPointSize = font.pointSize

            let full = NSRange(location: 0, length: (text as NSString).length)
            storage.beginEditing()
            storage.addAttribute(.font, value: font, range: full)
            storage.addAttribute(.foregroundColor, value: NSColor.labelColor, range: full)
            storage.removeAttribute(.backgroundColor, range: full)
            let color = NSColor.systemYellow.withAlphaComponent(0.35)
            for range in highlights {
                let nsRange = NSRange(location: range.lowerBound, length: range.count)
                if NSMaxRange(nsRange) <= full.length {
                    storage.addAttribute(.backgroundColor, value: color, range: nsRange)
                }
            }
            storage.endEditing()
            lastHighlights = highlights
        }

        func textViewDidChangeSelection(_ notification: Notification) {
            guard let textView else { return }
            let range = textView.selectedRange()
            if range.length > 0 {
                selection.wrappedValue = range.location..<(range.location + range.length)
            } else if selection.wrappedValue != nil {
                selection.wrappedValue = nil
            }
        }
    }
}
#else
import SwiftUI
import UIKit

/// iOS fallback: render-only selectable text. Highlight overlay + selection
/// capture are macOS-only for slice 1 (the Mac is the annotation surface); the
/// remote iOS client can still read and add page-scoped notes.
struct AnnotatableTextView: View {
    let text: String
    var highlights: [Range<Int>]
    @Binding var selection: Range<Int>?
    /// Reader text font scale (#3681). Scales the semantic `.body` base (which
    /// already tracks Dynamic Type) — never a hardcoded size.
    @AppStorage(ViewSettings.FontScale.readerKey)
    private var readerScale = ViewSettings.FontScale.defaultValue

    private var scaledSize: CGFloat {
        UIFont.preferredFont(forTextStyle: .body).pointSize
            * ViewSettings.FontScale.clamped(readerScale)
    }

    var body: some View {
        ScrollView {
            Text(text)
                .font(.system(size: scaledSize, design: .serif))
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
                .padding(8)
        }
    }
}
#endif
