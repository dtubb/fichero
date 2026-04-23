import AppKit
import SwiftUI

/// NSViewRepresentable for rich text editing with NSTextView
struct AttributedTextEditor: NSViewRepresentable {
    @Binding var text: NSAttributedString
    let isEditable: Bool
    let rulersVisible: Bool
    let fontName: String
    let fontSize: Double
    let lineSpacing: Double
    let marginH: Double
    let marginV: Double
    let contentRevision: Int
    let onTextChanged: () -> Void
    let onEditingChanged: (Bool) -> Void

    private var resolvedFont: NSFont {
        if fontName == "System" {
            return .systemFont(ofSize: CGFloat(fontSize))
        }
        return NSFont(name: fontName, size: CGFloat(fontSize))
            ?? .systemFont(ofSize: CGFloat(fontSize))
    }

    private func configureTextView(_ textView: NSTextView) {
        textView.isEditable = isEditable
        textView.isSelectable = true
        textView.isRichText = true
        textView.allowsUndo = true
        textView.allowsDocumentBackgroundColorChange = true
        textView.usesFindBar = true
        textView.usesInspectorBar = false
        textView.usesRuler = true
        textView.usesFontPanel = true
        textView.importsGraphics = true
        textView.isAutomaticTextCompletionEnabled = true
        textView.isContinuousSpellCheckingEnabled = true
        textView.isGrammarCheckingEnabled = true
        textView.isAutomaticSpellingCorrectionEnabled = true
        textView.isAutomaticQuoteSubstitutionEnabled = true
        textView.isAutomaticDashSubstitutionEnabled = true
        textView.isAutomaticTextReplacementEnabled = true
        textView.isAutomaticDataDetectionEnabled = true
        textView.isAutomaticLinkDetectionEnabled = true
        textView.enabledTextCheckingTypes = NSTextCheckingAllSystemTypes
        textView.drawsBackground = true
        textView.backgroundColor = .textBackgroundColor
        textView.textColor = .labelColor
        textView.font = resolvedFont
        textView.textContainerInset = NSSize(width: marginH, height: marginV)
        textView.defaultParagraphStyle = {
            let style = NSMutableParagraphStyle()
            style.lineSpacing = CGFloat(lineSpacing)
            return style
        }()
        textView.textContainer?.widthTracksTextView = true
        textView.isHorizontallyResizable = false
        textView.autoresizingMask = [.width]
    }

    func makeNSView(context: Context) -> NSScrollView {
        let scrollView = NSScrollView()
        scrollView.hasVerticalScroller = true
        scrollView.hasHorizontalScroller = false
        scrollView.hasHorizontalRuler = true
        scrollView.rulersVisible = rulersVisible
        scrollView.borderType = .noBorder
        scrollView.drawsBackground = true
        scrollView.backgroundColor = .textBackgroundColor
        scrollView.wantsLayer = true
        scrollView.layer?.masksToBounds = true

        let textView = NSTextView()
        configureTextView(textView)
        textView.delegate = context.coordinator
        context.coordinator.isApplyingModelUpdate = true
        textView.textStorage?.setAttributedString(text)
        context.coordinator.isApplyingModelUpdate = false

        scrollView.documentView = textView
        context.coordinator.textView = textView
        context.coordinator.lastAppliedRevision = contentRevision
        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = context.coordinator.textView else { return }
        textView.isEditable = isEditable
        scrollView.rulersVisible = rulersVisible

        textView.textContainerInset = NSSize(width: marginH, height: marginV)
        let paraStyle = NSMutableParagraphStyle()
        paraStyle.lineSpacing = CGFloat(lineSpacing)
        textView.defaultParagraphStyle = paraStyle
        textView.typingAttributes[.font] = resolvedFont
        textView.typingAttributes[.paragraphStyle] = paraStyle
        let typographySignature = "\(fontName)|\(fontSize)|\(lineSpacing)"

        // Only force-apply typography to existing text when the user actually changes
        // the default font/size/spacing in preferences — NOT on initial load. On load,
        // the decoded RTF may carry per-range fonts/colors the user set via the format
        // menu; blindly overwriting them strips their formatting on every reopen.
        let isInitialTypographyApply = context.coordinator.lastTypographySignature.isEmpty
        if context.coordinator.lastTypographySignature != typographySignature {
            if !isInitialTypographyApply,
               let textStorage = textView.textStorage,
               textStorage.length > 0 {
                let fullRange = NSRange(location: 0, length: textStorage.length)
                context.coordinator.isApplyingModelUpdate = true
                textStorage.addAttribute(.font, value: resolvedFont, range: fullRange)
                textStorage.addAttribute(.paragraphStyle, value: paraStyle, range: fullRange)
                context.coordinator.isApplyingModelUpdate = false
                text = textView.attributedString()
                onTextChanged()
            }
            context.coordinator.lastTypographySignature = typographySignature
        }

        if context.coordinator.lastAppliedRevision != contentRevision {
            let selectedRanges = textView.selectedRanges
            context.coordinator.isApplyingModelUpdate = true
            textView.textStorage?.setAttributedString(text)
            textView.setSelectedRanges(
                selectedRanges,
                affinity: textView.selectionAffinity,
                stillSelecting: false
            )
            context.coordinator.lastAppliedRevision = contentRevision
            context.coordinator.isApplyingModelUpdate = false
        }
    }

    final class Coordinator: NSObject, NSTextViewDelegate {
        @Binding var text: NSAttributedString
        weak var textView: NSTextView?
        var isApplyingModelUpdate = false
        var lastAppliedRevision = 0
        var lastTypographySignature = ""
        let onTextChanged: () -> Void
        let onEditingChanged: (Bool) -> Void

        init(
            text: Binding<NSAttributedString>,
            onTextChanged: @escaping () -> Void,
            onEditingChanged: @escaping (Bool) -> Void
        ) {
            _text = text
            self.onTextChanged = onTextChanged
            self.onEditingChanged = onEditingChanged
        }

        func textDidChange(_ notification: Notification) {
            guard let textView else { return }
            guard !isApplyingModelUpdate else { return }
            text = textView.attributedString()
            onTextChanged()
        }

        func textDidBeginEditing(_ notification: Notification) {
            onEditingChanged(true)
        }

        func textDidEndEditing(_ notification: Notification) {
            if let textView, !isApplyingModelUpdate {
                text = textView.attributedString()
                onTextChanged()
            }
            onEditingChanged(false)
        }
    }

    func makeCoordinator() -> Coordinator {
        Coordinator(
            text: $text,
            onTextChanged: onTextChanged,
            onEditingChanged: onEditingChanged
        )
    }
}
