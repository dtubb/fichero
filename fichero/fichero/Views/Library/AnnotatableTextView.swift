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

    private static var serifBodyFont: NSFont {
        let base = NSFont.preferredFont(forTextStyle: .body)
        return base.fontDescriptor.withDesign(.serif)
            .flatMap { NSFont(descriptor: $0, size: base.pointSize) } ?? base
    }

    func makeCoordinator() -> Coordinator { Coordinator(selection: $selection) }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.drawsBackground = false
        scrollView.borderType = .noBorder

        let textView = NSTextView()
        textView.delegate = context.coordinator
        textView.isEditable = false
        textView.isSelectable = true
        textView.drawsBackground = false
        textView.textContainerInset = NSSize(width: 8, height: 8)
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.lineFragmentPadding = 0

        context.coordinator.textView = textView
        scrollView.documentView = textView
        context.coordinator.apply(text: text, highlights: highlights, font: Self.serifBodyFont)
        return scrollView
    }

    func updateNSView(_ nsView: NSScrollView, context: Context) {
        context.coordinator.apply(text: text, highlights: highlights, font: Self.serifBodyFont)
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        private let selection: Binding<Range<Int>?>
        weak var textView: NSTextView?
        private var lastText: String?
        private var lastHighlights: [Range<Int>] = []

        init(selection: Binding<Range<Int>?>) { self.selection = selection }

        /// Sync content + highlight backgrounds. Cheap-guards on unchanged text
        /// and highlights so typing/scrolling doesn't rebuild attributes.
        func apply(text: String, highlights: [Range<Int>], font: NSFont) {
            guard let textView, let storage = textView.textStorage else { return }
            let textChanged = lastText != text
            if textChanged {
                textView.string = text
                lastText = text
            }
            guard textChanged || highlights != lastHighlights else { return }

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

/// iOS fallback: render-only selectable text. Highlight overlay + selection
/// capture are macOS-only for slice 1 (the Mac is the annotation surface); the
/// remote iOS client can still read and add page-scoped notes.
struct AnnotatableTextView: View {
    let text: String
    var highlights: [Range<Int>]
    @Binding var selection: Range<Int>?

    var body: some View {
        ScrollView {
            Text(text)
                .font(.system(.body, design: .serif))
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
                .padding(8)
        }
    }
}
#endif
