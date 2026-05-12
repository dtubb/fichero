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
        let height = ceil(used.height) + CGFloat(marginV) * 2
        // Sensible minimum so an empty editor still shows a line of room.
        return CGSize(width: proposedWidth, height: max(height, 24))
    }

    func updateNSView(_ scrollView: NSScrollView, context: Context) {
        guard let textView = context.coordinator.textView else { return }
        if controller?.textView !== textView { controller?.textView = textView }
        textView.isEditable = isEditable
        textView.usesInspectorBar = false
        // Only push rulersVisible into AppKit when it actually differs from
        // the current state. Otherwise we stomp AppKit's `toggleRuler:`
        // (Format > Text > Show Ruler) on every SwiftUI re-render and the
        // ruler appears not to toggle. The KVO observer in Coordinator
        // mirrors AppKit's writes back to @AppStorage to keep both in sync.
        if scrollView.rulersVisible != rulersVisible {
            context.coordinator.isApplyingRulerUpdate = true
            textView.usesRuler = rulersVisible
            scrollView.rulersVisible = rulersVisible
            context.coordinator.isApplyingRulerUpdate = false
        }
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
            // When the *content* changes (e.g., switched documents),
            // collapse the selection to the start. Preserving stale offsets
            // from the previous document would highlight unrelated text in
            // the new one. (#747)
            //
            // When only typography (font/size/lineSpacing) changed, the
            // earlier branch already wrote through and `text` here matches
            // current content — selection should stay put. We detect that
            // by comparing strings; if they match, keep selection.
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
        private weak var observedScrollView: NSScrollView?

        init(
            text: Binding<NSAttributedString>,
            onTextChanged: @escaping () -> Void,
            onEditingChanged: @escaping (Bool) -> Void
        ) {
            _text = text
            self.onTextChanged = onTextChanged
            self.onEditingChanged = onEditingChanged
        }

        deinit {
            observedScrollView?.removeObserver(self, forKeyPath: "rulersVisible")
        }

        func observeRulerVisibility(on scrollView: NSScrollView) {
            observedScrollView = scrollView
            scrollView.addObserver(self, forKeyPath: "rulersVisible", options: [.new], context: nil)
        }

        nonisolated override func observeValue(
            forKeyPath keyPath: String?,
            of object: Any?,
            change: [NSKeyValueChangeKey: Any]?,
            context: UnsafeMutableRawPointer?
        ) {
            guard keyPath == "rulersVisible",
                  let visible = change?[.newKey] as? Bool else { return }
            Task { @MainActor [weak self] in
                guard let self else { return }
                guard !self.isApplyingRulerUpdate else { return }
                self.onRulerVisibilityChanged?(visible)
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
