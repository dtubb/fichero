import SwiftUI

// MARK: - Preview head controls (Daniel, 2026-08-29, Preview.app as the model)
//
// The pane head gains the controls the bottom bar loses:
//   • pages ‹ › (and an up-to-parent step) LEFT of the breadcrumb — inside
//     the identity capsule, after the kind/lens selector;
//   • region show/hide + a renditions MENU top-right by the breadcrumb — the
//     reader's transcript/translation menu grammar;
//   • a pencil toggle that slides the markup row out UNDER the head.

/// The identity-capsule content: the Preview ∨ / Edit selector, then the
/// paging cluster (up-to-parent · ‹ ›) left of the breadcrumb.
struct PreviewHeadSelectorGroup: View {
    let selector: PaneKindSelector<PreviewLens>
    let chrome: PreviewPaneChrome
    /// Non-nil when the shown document HAS a visual parent (Daniel,
    /// 2026-08-29: a region/page-part needs an obvious one-click way BACK UP
    /// to the spread). Invoking it shows the parent in this pane.
    var onUpToParent: (() -> Void)?

    var body: some View {
        selector

        Divider().frame(height: PaneHeadMetrics.dividerHeight)

        if let onUpToParent {
            Button(action: onUpToParent) {
                Image(systemName: "chevron.up")
                    .font(.callout)
            }
            .buttonStyle(.borderless)
            .help("Up to the parent image")
            .accessibilityLabel("Up to the parent image")
            .accessibilityIdentifier("previewHeadUpToParent")
        }

        pageArrows
    }

    /// ‹ › page/sibling stepping. Uses the canvas-published nav when there is
    /// one (PDF pages; image sibling walk with position), else falls back to
    /// the sibling-swipe seam so the arrows always work — the reliable
    /// alternative to the swipe the scroll view eats (ruling 6).
    @ViewBuilder
    private var pageArrows: some View {
        let nav = chrome.pageNav
        Button {
            if let nav { nav.goPrevious() } else {
                NotificationCenter.default.post(name: .previewSiblingSwipe, object: -1)
            }
        } label: {
            Image(systemName: "chevron.left").font(.callout)
        }
        .buttonStyle(.borderless)
        .disabled(nav.map { !$0.canGoPrevious } ?? false)
        .help("Previous page")
        .accessibilityLabel("Previous page")
        .accessibilityIdentifier("previewHeadPreviousPage")

        if let nav {
            Text("\(nav.pageIndex + 1)/\(nav.pageCount)")
                .font(.caption)
                .monospacedDigit()
                .foregroundStyle(.secondary)
        }

        Button {
            if let nav { nav.goNext() } else {
                NotificationCenter.default.post(name: .previewSiblingSwipe, object: 1)
            }
        } label: {
            Image(systemName: "chevron.right").font(.callout)
        }
        .buttonStyle(.borderless)
        .disabled(nav.map { !$0.canGoNext } ?? false)
        .help("Next page")
        .accessibilityLabel("Next page")
        .accessibilityIdentifier("previewHeadNextPage")
    }
}

/// The head's top-right lenses: region show/hide, and the renditions menu.
struct PreviewHeadLensControls: View {
    let chrome: PreviewPaneChrome

    /// One user-facing toggle over both canvases' overlay switches — the
    /// image and PDF keys stay distinct in storage (they gate different
    /// loaders) but the head flips them together: "show regions" is one lens.
    @AppStorage("imagePreview.ocrBoxesEnabled") private var imageBoxesEnabled = true
    @AppStorage("pdfPreview.ocrBoxesEnabled") private var pdfBoxesEnabled = true

    var body: some View {
        regionToggle
        renditionsMenu
    }

    private var regionToggle: some View {
        Button {
            let show = !imageBoxesEnabled
            imageBoxesEnabled = show
            pdfBoxesEnabled = show
        } label: {
            Image(systemName: imageBoxesEnabled ? "square.dashed.inset.filled" : "square.dashed")
        }
        .buttonStyle(.borderless)
        .foregroundStyle(imageBoxesEnabled ? Color.accentColor : Color.secondary)
        .help(imageBoxesEnabled ? "Hide regions" : "Show regions")
        .accessibilityLabel(imageBoxesEnabled ? "Hide regions" : "Show regions")
        .accessibilityIdentifier("previewHeadRegionToggle")
    }

    /// Renditions as a MENU, the reader's transcript/translation grammar
    /// (Daniel, 2026-08-29) — hidden when the page has at most one rendition.
    @ViewBuilder
    private var renditionsMenu: some View {
        if chrome.renditionNames.count > 1 {
            Menu {
                ForEach(Array(chrome.renditionNames.enumerated()), id: \.offset) { index, name in
                    Button {
                        chrome.selectRendition?(index)
                    } label: {
                        if index == chrome.renditionIndex {
                            Label(name, systemImage: "checkmark")
                        } else {
                            Text(name)
                        }
                    }
                }
            } label: {
                Text(currentRenditionName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Which rendition of this page is showing")
            .accessibilityLabel("Renditions")
            .accessibilityIdentifier("previewHeadRenditionsMenu")
        }
    }

    private var currentRenditionName: String {
        let names = chrome.renditionNames
        guard names.indices.contains(chrome.renditionIndex) else { return "Rendition" }
        return names[chrome.renditionIndex]
    }
}

// MARK: - The slide-out markup row

/// Preview.app's markup bar (Daniel, 2026-08-29): slides out UNDER the head
/// when the head's pencil is toggled, over the image. Select / draw-region /
/// line / highlight (split button) / text note / delete / combine.
///
/// Highlight and note arm the EXISTING AnnotationStore path (the canvases
/// observe `.previewAnnotateTool`). Select / draw-region / delete / combine
/// post `.previewRegionVerb` — the seam the preview-regions lane fills.
struct PreviewMarkupToolsRow: View {
    /// Sticky tool state (Daniel, 2026-08-30: "leave it selected") — the
    /// armed MODE lives per-window; optional so headless hosts stay safe.
    @Environment(WindowState.self) private var windowState: WindowState?

    @AppStorage(PreviewHighlightStyle.storageKey) private var highlightStyleRaw
        = PreviewHighlightStyle.yellow.rawValue

    private var highlightStyle: PreviewHighlightStyle {
        PreviewHighlightStyle(rawValue: highlightStyleRaw) ?? .yellow
    }

    /// Icon-and-Text (Daniel, 2026-08-30): labels render beneath the glyphs
    /// when the window's label mode is on — same switch as the workflow bar.
    var showsLabels = false

    // Order ruled 2026-08-30: text selection FIRST (Preview.app's A|), then
    // marquee, then the rest.
    var body: some View {
        toolButton(
            icon: PreviewMarkupTool.textSelect.icon,
            label: PreviewMarkupTool.textSelect.label,
            identifier: "previewMarkupTextSelect",
            mode: .textSelect
        ) {
            NotificationCenter.default.post(
                name: .previewAnnotateTool, object: PreviewMarkupTool.textSelect.rawValue
            )
        }

        toolButton(
            icon: PreviewMarkupTool.drawRegion.icon,
            label: PreviewMarkupTool.drawRegion.label,
            identifier: "previewMarkupDrawRegion",
            mode: .drawRegion
        ) {
            NotificationCenter.default.post(
                name: .previewRegionVerb, object: PreviewRegionVerb.draw.rawValue
            )
        }

        toolButton(
            icon: PreviewMarkupTool.select.icon,
            label: PreviewMarkupTool.select.label,
            identifier: "previewMarkupSelect",
            mode: .select
        ) {
            NotificationCenter.default.post(
                name: .previewRegionVerb, object: PreviewRegionVerb.select.rawValue
            )
        }

        toolButton(
            icon: PreviewMarkupTool.line.icon,
            label: PreviewMarkupTool.line.label,
            identifier: "previewMarkupLine",
            mode: .line
        ) {
            NotificationCenter.default.post(
                name: .previewAnnotateTool, object: PreviewMarkupTool.line.rawValue
            )
        }

        labeled(PreviewMarkupTool.highlight.label) { highlightSplitButton }

        toolButton(
            icon: PreviewMarkupTool.note.icon,
            label: PreviewMarkupTool.note.label,
            identifier: "previewMarkupNote",
            mode: .note
        ) {
            NotificationCenter.default.post(
                name: .previewAnnotateTool, object: PreviewMarkupTool.note.rawValue
            )
        }

        toolButton(
            icon: PreviewMarkupTool.star.icon,
            label: PreviewMarkupTool.star.label,
            identifier: "previewMarkupStar"
        ) {
            NotificationCenter.default.post(
                name: .previewAnnotateTool, object: PreviewMarkupTool.star.rawValue
            )
        }

        Divider().frame(height: PaneHeadMetrics.dividerHeight)

        toolButton(icon: "trash", label: "Delete", identifier: "previewMarkupDelete") {
            NotificationCenter.default.post(
                name: .previewRegionVerb, object: PreviewRegionVerb.delete.rawValue
            )
        }

        toolButton(icon: "arrow.triangle.merge", label: "Combine", identifier: "previewMarkupCombine") {
            NotificationCenter.default.post(
                name: .previewRegionVerb, object: PreviewRegionVerb.combine.rawValue
            )
        }
    }

    /// Caption under any control when labels are on (the workflow-bar idiom).
    @ViewBuilder
    private func labeled(_ text: String, @ViewBuilder content: () -> some View) -> some View {
        if showsLabels {
            VStack(spacing: 2) {
                content()
                Text(text).font(.caption2).foregroundStyle(.secondary)
            }
        } else {
            content()
        }
    }

    /// The SPLIT highlight button (Daniel, 2026-08-29, Preview.app
    /// screenshot): the glyph arms highlighting with the CURRENT style; the
    /// chevron opens the five colors (filled dots) then Underline /
    /// Strikethrough as checkable modes. The choice persists as the button's
    /// state (AppStorage), and the color rides each saved highlight.
    private var highlightSplitButton: some View {
        HStack(spacing: 0) {
            Button {
                let armed = windowState?.activeMarkupTool == .highlight
                windowState?.activeMarkupTool = armed ? nil : .highlight
                if armed { return }
                NotificationCenter.default.post(
                    name: .previewAnnotateTool, object: PreviewMarkupTool.highlight.rawValue
                )
            } label: {
                Image(systemName: "highlighter")
                    .foregroundStyle(windowState?.activeMarkupTool == .highlight
                        ? AnyShapeStyle(Color.accentColor)
                        : AnyShapeStyle(highlightStyle.tint))
            }
            .buttonStyle(.borderless)
            .help("Highlight (\(highlightStyle.label))")
            .accessibilityLabel("Highlight, \(highlightStyle.label)")
            .accessibilityIdentifier("previewMarkupHighlight")

            Menu {
                ForEach(PreviewHighlightStyle.colors) { style in
                    styleRow(style)
                }
                Divider()
                styleRow(.underline)
                styleRow(.strikethrough)
            } label: {
                Image(systemName: "chevron.down")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Highlight color and mode")
            .accessibilityLabel("Highlight color and mode")
            .accessibilityIdentifier("previewMarkupHighlightMenu")
        }
    }

    private func styleRow(_ style: PreviewHighlightStyle) -> some View {
        PreviewHighlightStyleMenu.styleRow(
            style, current: highlightStyle
        ) { highlightStyleRaw = $0.rawValue }
    }

    private func toolButton(
        icon: String, label: String, identifier: String,
        mode: PreviewMarkupTool? = nil, action: @escaping () -> Void
    ) -> some View {
        let armed = mode != nil && windowState?.activeMarkupTool == mode
        return labeled(label) {
            Button {
                // MODE buttons stay selected (sticky) until toggled off or
                // another mode arms; plain buttons are one-shot verbs.
                if let mode {
                    let next: PreviewMarkupTool? = armed ? nil : mode
                    windowState?.activeMarkupTool = next
                    if next == nil { return }
                }
                action()
            } label: {
                Image(systemName: icon)
            }
            .buttonStyle(.borderless)
            .foregroundStyle(armed ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary))
            .help(label)
            .accessibilityLabel(label)
            .accessibilityIdentifier(identifier)
        }
    }
}

/// The highlight-style chevron menu, shared by the annotation bar's split
/// button and the toolbar pencil (Daniel, 2026-08-30): colors, then
/// Underline / Strikethrough as checkable modes. One storage key, so the
/// choice travels with every highlight wherever it is drawn.
struct PreviewHighlightStyleMenu: View {
    @AppStorage(PreviewHighlightStyle.storageKey) private var highlightStyleRaw
        = PreviewHighlightStyle.yellow.rawValue

    private var current: PreviewHighlightStyle {
        PreviewHighlightStyle(rawValue: highlightStyleRaw) ?? .yellow
    }

    var body: some View {
        Menu {
            ForEach(PreviewHighlightStyle.colors) { style in
                Self.styleRow(style, current: current) { highlightStyleRaw = $0.rawValue }
            }
            Divider()
            Self.styleRow(.underline, current: current) { highlightStyleRaw = $0.rawValue }
            Self.styleRow(.strikethrough, current: current) { highlightStyleRaw = $0.rawValue }
        } label: {
            Image(systemName: "chevron.down")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Highlight color and mode")
        .accessibilityLabel("Highlight color and mode")
        .accessibilityIdentifier("annotationHighlightStyleMenu")
    }

    static func styleRow(
        _ style: PreviewHighlightStyle,
        current: PreviewHighlightStyle,
        select: @escaping (PreviewHighlightStyle) -> Void
    ) -> some View {
        Button {
            select(style)
        } label: {
            if style.isColor {
                Label(style.label, systemImage: "circle.fill")
            } else {
                Label(
                    style.label,
                    systemImage: style == .underline ? "underline" : "strikethrough"
                )
            }
            if style == current {
                Image(systemName: "checkmark")
            }
        }
        .tint(style.tint)
    }
}
