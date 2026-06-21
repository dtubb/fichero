#if canImport(AppKit)
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
    /// Called when AppKit's `toggleRuler:` (Format > Text > Show Ruler) flips
    /// the scrollView's `rulersVisible`. Lets the inspector mirror that back
    /// to its `@AppStorage("editor.rulersVisible")` so all editors stay in
    /// sync and the menu validation sees correct state. (#781 follow-up)
    var onRulerVisibilityChanged: ((Bool) -> Void)?

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
        // Also delegate the text storage so attribute-only edits (bold,
        // italic, paragraph styles) propagate to our @Binding. NSTextView's
        // `textDidChange(_:)` fires only on text-content changes; attribute
        // changes go through textStorage's didProcessEditing instead. (#746)
        textView.textStorage?.delegate = context.coordinator
        context.coordinator.isApplyingModelUpdate = true
        textView.textStorage?.setAttributedString(text)
        context.coordinator.isApplyingModelUpdate = false

        scrollView.documentView = textView
        // rulersVisible MUST be set AFTER documentView is attached. Setting it
        // earlier silently no-ops because NSScrollView has no ruler accessory
        // to install yet — the textView provides it. Once attached, AppKit
        // wires the accessory and rulersVisible takes effect (#781).
        scrollView.rulersVisible = rulersVisible
        context.coordinator.textView = textView
        context.coordinator.lastAppliedRevision = contentRevision
        // KVO on scrollView.rulersVisible so AppKit's auto-injected
        // Format > Text > Show Ruler menu (which calls `toggleRuler:`) can
        // flip the ruler and have us mirror it back to @AppStorage. Without
        // this, the menu validation reads stale state and the label never
        // says "Hide Ruler" (#781 follow-up).
        context.coordinator.observeRulerVisibility(on: scrollView)
        controller?.textView = textView

        return scrollView
    }

    /// Report the editor's natural layout height to SwiftUI so the parent
    /// panel sizes to actual content instead of filling the outer ScrollView
    /// viewport. Fixes #960: without this, NSViewRepresentable has no
    /// intrinsic vertical size, the panel's .frame(maxHeight: .infinity)
    /// took every available pt, and the outer ScrollView ended up with one
    /// panel per screen regardless of content length.
    func sizeThatFits(
        _ proposal: ProposedViewSize,
        nsView: NSScrollView,
        context: Context
    ) -> CGSize? {
        guard let textView = nsView.documentView as? NSTextView,
              let layoutManager = textView.layoutManager,
              let textContainer = textView.textContainer
        else { return nil }
        let proposedWidth = proposal.width ?? nsView.bounds.width
        // Account for the NSScrollView's leading/trailing insets — those
        // come out of the container width, not the editor's reported width.
        let containerWidth = max(0, proposedWidth - leadingInset - trailingInset)
        if abs(textContainer.size.width - containerWidth) > 0.5 {
            textContainer.size = NSSize(
                width: containerWidth,
                height: .greatestFiniteMagnitude
            )
        }
        layoutManager.ensureLayout(for: textContainer)
        let used = layoutManager.usedRect(for: textContainer)
        // marginV is the textContainerInset top+bottom; double it.
        let contentHeight = ceil(used.height) + CGFloat(marginV) * 2
        // When a finite height is proposed (bounded container, e.g. the
        // page-content-only inspector pane with no outer ScrollView), honour
        // the proposal so SwiftUI's layout stays correct and the NSScrollView
        // handles long content internally. Returning the full content height
        // here caused the SwiftUI layout to overflow, blocking the inspector
        // tab bar (#2309). In an unbounded context (nil proposal, e.g. inside
        // a ScrollView), report actual content height for per-panel sizing (#960).
        if let ph = proposal.height, ph.isFinite, ph > 0 {
            return CGSize(width: proposedWidth, height: max(ph, 24))
        }
        return CGSize(width: proposedWidth, height: max(contentHeight, 24))
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = context.coordinator.textView else { return }
        if controller?.textView !== textView { controller?.textView = textView }
        let configuration = TextViewStateConfiguration(
            isEditable: isEditable,
            rulersVisible: rulersVisible,
            leadingInset: leadingInset,
            trailingInset: trailingInset,
            marginV: marginV
        )
        configureTextViewState(scrollView, textView: textView, context: context, configuration: configuration)
        applyTypographyIfNeeded(to: textView, context: context)
        applyContentIfNeeded(to: textView, context: context)
    }

    private func applyTypographyIfNeeded(to textView: NSTextView, context: Context) {
        let paraStyle = NSMutableParagraphStyle()
        paraStyle.lineSpacing = CGFloat(lineSpacing)
        textView.defaultParagraphStyle = paraStyle
        textView.typingAttributes[.font] = resolvedFont
        textView.typingAttributes[.paragraphStyle] = paraStyle

        let typographySignature = "\(fontName)|\(fontSize)|\(lineSpacing)"
        let isInitialTypographyApply = context.coordinator.lastTypographySignature.isEmpty
        guard context.coordinator.lastTypographySignature != typographySignature else { return }

        if !isInitialTypographyApply,
           let textStorage = textView.textStorage,
           textStorage.length > 0 {
            let fullRange = NSRange(location: 0, length: textStorage.length)
            context.coordinator.isApplyingModelUpdate = true
            textStorage.addAttribute(.font, value: resolvedFont, range: fullRange)
            textStorage.addAttribute(.paragraphStyle, value: paraStyle, range: fullRange)
            context.coordinator.isApplyingModelUpdate = false
            let updated = textView.attributedString()
            let onTextChangedCallback = onTextChanged
            DispatchQueue.main.async {
                text = updated
                onTextChangedCallback()
            }
        }
        context.coordinator.lastTypographySignature = typographySignature
    }

    private func applyContentIfNeeded(to textView: NSTextView, context: Context) {
        guard context.coordinator.lastAppliedRevision != contentRevision else { return }

        let isContentSwap = (textView.string != text.string)
        let preservedRanges = textView.selectedRanges
        context.coordinator.isApplyingModelUpdate = true
        textView.textStorage?.setAttributedString(text)
        if isContentSwap {
            textView.setSelectedRange(NSRange(location: 0, length: 0))
        } else {
            textView.setSelectedRanges(
                preservedRanges,
                affinity: textView.selectionAffinity,
                stillSelecting: false
            )
        }
        context.coordinator.lastAppliedRevision = contentRevision
        context.coordinator.isApplyingModelUpdate = false
    }

    @MainActor
    final class Coordinator: NSObject, NSTextViewDelegate, NSTextStorageDelegate {
        @Binding var text: NSAttributedString
        weak var textView: NSTextView?

        var isApplyingModelUpdate = false
        var isApplyingRulerUpdate = false
        var lastAppliedRevision = 0
        var lastTypographySignature = ""
        let onTextChanged: () -> Void
        let onEditingChanged: (Bool) -> Void
        var onRulerVisibilityChanged: ((Bool) -> Void)?
        private var rulerObservation: NSKeyValueObservation?

        init(
            text: Binding<NSAttributedString>,
            onTextChanged: @escaping () -> Void,
            onEditingChanged: @escaping (Bool) -> Void
        ) {
            _text = text
            self.onTextChanged = onTextChanged
            self.onEditingChanged = onEditingChanged
        }

        func observeRulerVisibility(on scrollView: NSScrollView) {
            rulerObservation = scrollView.observe(\.rulersVisible, options: [.new]) { [weak self] _, change in
                guard let visible = change.newValue else { return }
                Task { @MainActor [weak self] in
                    guard let self else { return }
                    guard !self.isApplyingRulerUpdate else { return }
                    self.onRulerVisibilityChanged?(visible)
                }
            }
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

        // MARK: - NSTextStorageDelegate

        /// Catches attribute-only edits — bold, italic, underline, color,
        /// paragraph styles, ruler tab stops — that NSTextView's
        /// `textDidChange(_:)` does NOT fire for. (#746)
        ///
        /// `editedMask` tells us what kind of edit happened:
        ///   - `.editedCharacters` — text content changed (already covered
        ///     by `textDidChange`, no-op here to avoid double-write)
        ///   - `.editedAttributes` — only attributes changed (bold/etc.) —
        ///     update the binding so `performSave` sees the new RTF
        nonisolated func textStorage(
            _ textStorage: NSTextStorage,
            didProcessEditing editedMask: NSTextStorageEditActions,
            range editedRange: NSRange,
            changeInLength delta: Int
        ) {
            // Only care about attribute-only edits — character edits are
            // already handled by textDidChange, and dispatching twice would
            // cause the auto-save timer to thrash.
            guard editedMask.contains(.editedAttributes),
                  !editedMask.contains(.editedCharacters) else { return }
            // Hop to the main actor to read the text view + write the
            // binding. The NSTextStorageDelegate protocol is nonisolated,
            // but in practice this call comes from main-thread NSTextView
            // edits — Task @MainActor formalizes that for Swift 6.
            // Also defers the binding write past the storage's editing
            // transaction, dodging the "Modifying state during view
            // update" warning.
            Task { @MainActor [weak self] in
                guard let self else { return }
                guard !self.isApplyingModelUpdate else { return }
                guard let textView = self.textView else { return }
                self.text = textView.attributedString()
                self.onTextChanged()
            }
        }
    }

    func makeCoordinator() -> Coordinator {
        let coordinator = Coordinator(
            text: $text,
            onTextChanged: onTextChanged,
            onEditingChanged: onEditingChanged
        )
        coordinator.onRulerVisibilityChanged = onRulerVisibilityChanged
        return coordinator
    }
}

@MainActor
private func configureTextViewState(
    _ scrollView: NSScrollView,
    textView: NSTextView,
    context: AttributedTextEditor.Context,
    configuration: TextViewStateConfiguration
) {
    textView.isEditable = configuration.isEditable
    textView.usesInspectorBar = false
    // Re-affirm horizontal clamping on every update so no reconfiguration
    // (ruler toggle, content reseed, typography change) can leave the text
    // view horizontally resizable and let it paint past the inspector pane
    // width (#2477). The container tracks the view's width; the view never
    // grows horizontally beyond its frame, so text always wraps to the pane.
    textView.isHorizontallyResizable = false
    textView.textContainer?.widthTracksTextView = true
    if scrollView.rulersVisible != configuration.rulersVisible {
        context.coordinator.isApplyingRulerUpdate = true
        textView.usesRuler = configuration.rulersVisible
        scrollView.rulersVisible = configuration.rulersVisible
        context.coordinator.isApplyingRulerUpdate = false
    }
    scrollView.contentInsets = NSEdgeInsets(
        top: 0,
        left: configuration.leadingInset,
        bottom: 0,
        right: configuration.trailingInset
    )
    textView.textContainerInset = NSSize(width: 0, height: configuration.marginV)
}

private struct TextViewStateConfiguration {
    let isEditable: Bool
    let rulersVisible: Bool
    let leadingInset: CGFloat
    let trailingInset: CGFloat
    let marginV: Double
}
#elseif canImport(UIKit)
import UIKit
import SwiftUI

@MainActor
final class RichTextController: ObservableObject {
    weak var textView: UITextView?

    func toggleTrait(_ selector: Selector) {
        guard let textView else { return }
        _ = textView.perform(selector, with: nil)
    }
}

struct AttributedTextEditor: UIViewRepresentable {
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
    var onRulerVisibilityChanged: ((Bool) -> Void)?
    var marginLeading: Double?
    var marginTrailing: Double?
    var controller: RichTextController?

    private var leadingInset: CGFloat { CGFloat(marginLeading ?? marginH) }
    private var trailingInset: CGFloat { CGFloat(marginTrailing ?? marginH) }

    private var resolvedFont: UIFont {
        if fontName == "System" {
            return .systemFont(ofSize: CGFloat(fontSize))
        }
        return UIFont(name: fontName, size: CGFloat(fontSize))
            ?? .systemFont(ofSize: CGFloat(fontSize))
    }

    func makeUIView(context: Context) -> UITextView {
        let textView = UITextView()
        textView.isEditable = isEditable
        textView.isSelectable = true
        textView.allowsEditingTextAttributes = true
        textView.delegate = context.coordinator
        textView.attributedText = text
        textView.backgroundColor = .systemBackground
        textView.textColor = .label
        textView.font = resolvedFont
        textView.textContainerInset = UIEdgeInsets(
            top: CGFloat(marginV),
            left: leadingInset,
            bottom: CGFloat(marginV),
            right: trailingInset
        )
        let paraStyle = NSMutableParagraphStyle()
        paraStyle.lineSpacing = CGFloat(lineSpacing)
        let attrs: [NSAttributedString.Key: Any] = [
            .font: resolvedFont,
            .paragraphStyle: paraStyle,
            .foregroundColor: UIColor.label
        ]
        textView.typingAttributes = attrs
        context.coordinator.textView = textView
        context.coordinator.lastAppliedRevision = contentRevision
        controller?.textView = textView
        return textView
    }

    func updateUIView(_ textView: UITextView, context: Context) {
        if controller?.textView !== textView { controller?.textView = textView }
        textView.isEditable = isEditable
        textView.textContainerInset = UIEdgeInsets(
            top: CGFloat(marginV),
            left: leadingInset,
            bottom: CGFloat(marginV),
            right: trailingInset
        )
        guard context.coordinator.lastAppliedRevision != contentRevision else { return }
        context.coordinator.isApplyingModelUpdate = true
        textView.attributedText = text
        context.coordinator.lastAppliedRevision = contentRevision
        context.coordinator.isApplyingModelUpdate = false
    }

    @MainActor
    final class Coordinator: NSObject, UITextViewDelegate {
        @Binding var text: NSAttributedString
        weak var textView: UITextView?
        var isApplyingModelUpdate = false
        var lastAppliedRevision = 0
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

        func textViewDidChange(_ textView: UITextView) {
            guard !isApplyingModelUpdate else { return }
            text = textView.attributedText
            onTextChanged()
        }

        func textViewDidBeginEditing(_ textView: UITextView) {
            onEditingChanged(true)
        }

        func textViewDidEndEditing(_ textView: UITextView) {
            if !isApplyingModelUpdate {
                text = textView.attributedText
                onTextChanged()
            }
            onEditingChanged(false)
        }
    }

    func makeCoordinator() -> Coordinator {
        let coordinator = Coordinator(
            text: $text,
            onTextChanged: onTextChanged,
            onEditingChanged: onEditingChanged
        )
        return coordinator
    }
}

#endif

