#if canImport(AppKit)
import AppKit
import SwiftUI

/// AppKit-backed plain text editor with native macOS editing behaviors.
struct MacPlainTextEditor: NSViewRepresentable {
    @Binding var text: String
    var font: NSFont = .preferredFont(forTextStyle: .body)
    var isEditable: Bool = true
    var isSelectable: Bool = true

    func makeCoordinator() -> Coordinator {
        Coordinator(text: $text)
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.autohidesScrollers = true
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = false

        let textView = NSTextView()
        textView.delegate = context.coordinator
        textView.string = text
        textView.font = font
        textView.isRichText = false
        textView.isEditable = isEditable
        textView.isSelectable = isSelectable
        textView.isAutomaticQuoteSubstitutionEnabled = true
        textView.isAutomaticDashSubstitutionEnabled = true
        textView.isAutomaticTextReplacementEnabled = true
        textView.isAutomaticSpellingCorrectionEnabled = true
        textView.isContinuousSpellCheckingEnabled = true
        textView.isGrammarCheckingEnabled = true
        textView.isIncrementalSearchingEnabled = true
        textView.usesFindPanel = true
        textView.usesFontPanel = true
        textView.allowsUndo = true
        textView.backgroundColor = .clear
        textView.textContainerInset = NSSize(width: 4, height: 6)
        textView.textContainer?.widthTracksTextView = true
        textView.textContainer?.lineFragmentPadding = 0

        context.coordinator.textView = textView
        scrollView.documentView = textView
        return scrollView
    }

    func updateNSView(_ nsView: NSScrollView, context: Context) {
        guard let textView = context.coordinator.textView else { return }
        textView.font = font
        textView.isEditable = isEditable
        textView.isSelectable = isSelectable
        if textView.string != text {
            textView.string = text
        }
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        private var text: Binding<String>
        weak var textView: NSTextView?

        init(text: Binding<String>) {
            self.text = text
        }

        func textDidChange(_ notification: Notification) {
            guard let textView else { return }
            text.wrappedValue = textView.string
        }
    }
}
#elseif canImport(UIKit)
import SwiftUI
import UIKit

/// iOS plain text editor using SwiftUI's native TextEditor.
struct MacPlainTextEditor: View {
    @Binding var text: String
    var font: UIFont = .preferredFont(forTextStyle: .body)
    var isEditable: Bool = true
    var isSelectable: Bool = true

    var body: some View {
        TextEditor(text: $text)
            .font(Font(font))
            .disabled(!isEditable)
    }
}

#endif
