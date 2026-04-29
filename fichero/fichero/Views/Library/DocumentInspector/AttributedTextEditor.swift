import AppKit
import SwiftUI

/// Holds a weak reference to the NSTextView backing an AttributedTextEditor so
/// a SwiftUI format toolbar (bold/italic/underline/etc.) can drive it without
/// the textview having to be first responder.
@MainActor
final class RichTextController: ObservableObject {
    weak var textView: NSTextView?

    func toggleTrait(_ selector: Selector) {
        guard let textView else { return }
        _ = textView.perform(selector, with: nil)
    }
}

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

    // Asymmetric horizontal padding. Default to symmetric `marginH` for back-compat
    // with V1 inspector callers; V2 inspector overrides trailing to 0 so the
    // editor reaches the panel's right edge (flush with the scrollbar).
    var marginLeading: Double?
    var marginTrailing: Double?
    var controller: RichTextController?

    private var leadingInset: CGFloat { CGFloat(marginLeading ?? marginH) }
    private var trailingInset: CGFloat { CGFloat(marginTrailing ?? marginH) }

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
        // AppKit's inspector bar attaches at the window scope (above tabs),
        // not above the text view itself — wrong place for our per-panel
        // editor. We render a SwiftUI format bar above the editor in
        // ArtifactPanel instead.
        textView.usesInspectorBar = false
        // Bind usesRuler to the global toggle so the ruler can NEVER pop in
        // when the user clicks to edit. Either it shows always, or never.
        textView.usesRuler = rulersVisible
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
        // textContainerInset is symmetric in AppKit. Use 0 here and let
        // the surrounding NSScrollView's contentInsets carry asymmetric
        // leading/trailing padding (set in makeNSView/updateNSView).
        textView.textContainerInset = NSSize(width: 0, height: marginV)
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
        scrollView.automaticallyAdjustsContentInsets = false
        scrollView.contentInsets = NSEdgeInsets(
            top: 0, left: leadingInset, bottom: 0, right: trailingInset
        )
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
        controller?.textView = textView

        return scrollView
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = context.coordinator.textView else { return }
        if controller?.textView !== textView { controller?.textView = textView }
        textView.isEditable = isEditable
        textView.usesRuler = rulersVisible
        textView.usesInspectorBar = false
        scrollView.rulersVisible = rulersVisible
        scrollView.contentInsets = NSEdgeInsets(
            top: 0, left: leadingInset, bottom: 0, right: trailingInset
        )

        textView.textContainerInset = NSSize(width: 0, height: marginV)
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
                // Writing to @Binding `text` directly from inside updateNSView
                // triggers 'Modifying state during view update' warnings — SwiftUI
                // is actively re-rendering us. Defer the binding write (and the
                // derived onTextChanged callback) to the next runloop so we're
                // past the update phase. Daniel report 2026-04-24.
                let updated = textView.attributedString()
                let onTextChangedCallback = onTextChanged
                DispatchQueue.main.async {
                    text = updated
                    onTextChangedCallback()
                }
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
