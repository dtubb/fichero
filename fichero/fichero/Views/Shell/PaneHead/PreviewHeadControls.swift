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
            // Not a bare chevron.up (Daniel, 2026-09-02): sitting beside the
            // page arrows it read as "rendition up" — an axis it isn't. The
            // turn-up glyph says "go up a level", which is what it does.
            Button(action: onUpToParent) {
                Image(systemName: "arrow.turn.left.up")
                    .font(.callout)
            }
            .buttonStyle(.borderless)
            // No key binding for the three nav controls here: ⌘[ / ⌘] belong
            // to `CanvasMenuCommands` and ⌘⌥[ / ⌘⌥] to the magnifier's zoom
            // in `ImagePreviewMenuCommands`. A second view binding the same
            // chord doesn't win, it just makes one of the two stop working.
            .help("Up to the parent image — show the spread this part came from")
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
        .help("Previous page in this document")
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
        .help("Next page in this document")
        .accessibilityLabel("Next page")
        .accessibilityIdentifier("previewHeadNextPage")
    }
}

/// The head's top-right lenses: the zoom-cluster toggle, and the renditions
/// menu.
struct PreviewHeadLensControls: View {
    let chrome: PreviewPaneChrome

    /// Whether the floating magnification cluster (mini-map / zoom pill /
    /// loupe + magnifier toggles) is showing over the canvas.
    @AppStorage("imagePreview.zoomControlsVisible") private var zoomControlsVisible = true

    var body: some View {
        zoomControlsToggle
        renditionSteppers
        renditionsMenu
    }

    /// ▲▼ rendition stepping RIGHT of the breadcrumb (Daniel, 2026-09-02:
    /// "left right to left of breadcrumb, renditions to right of breadcrumbs").
    /// The vertical swipe flips the same axis; these buttons make it VISIBLE —
    /// a page with one rendition shows nothing, which is why the axis felt
    /// dead on documents that had nothing to flip to.
    @ViewBuilder
    private var renditionSteppers: some View {
        if chrome.renditionNames.count > 1 {
            Button {
                chrome.selectRendition?(chrome.renditionIndex - 1)
            } label: {
                Image(systemName: "chevron.up").font(.callout)
            }
            .buttonStyle(.borderless)
            .disabled(chrome.renditionIndex <= 0)
            .help("Previous rendition of this page (swipe up)")
            .accessibilityLabel("Previous rendition")
            .accessibilityIdentifier("previewHeadRenditionPrevious")

            Button {
                chrome.selectRendition?(chrome.renditionIndex + 1)
            } label: {
                Image(systemName: "chevron.down").font(.callout)
            }
            .buttonStyle(.borderless)
            .disabled(chrome.renditionIndex >= chrome.renditionNames.count - 1)
            .help("Next rendition of this page (swipe down)")
            .accessibilityLabel("Next rendition")
            .accessibilityIdentifier("previewHeadRenditionNext")
        }
    }

    /// The word-boundaries toggle that used to sit here is GONE (Daniel,
    /// 2026-08-31: "not needed as bottom metadata has that"). It was also the
    /// desync: it wrote `imagePreview.ocrBoxesEnabled` AND
    /// `pdfPreview.ocrBoxesEnabled` while labelling itself "regions", so the
    /// head and the bottom menu disagreed about which switch was which. One
    /// owner now — the quiet bar's what-to-show menu — and this seat goes to
    /// the control the head actually lacked.
    private var zoomControlsToggle: some View {
        Button {
            zoomControlsVisible.toggle()
        } label: {
            // ONE icon, both states (Daniel, 2026-09-01). Swapping the glyph
            // for +/− made the button read as "zoom in" / "zoom out" rather
            // than "show the zoom controls" — a toggle whose picture changes
            // is a different button. The loupe-with-a-plus stays put; only the
            // tint says whether the cluster is on.
            Image(systemName: "plus.magnifyingglass")
        }
        .buttonStyle(.borderless)
        .foregroundStyle(zoomControlsVisible ? Color.accentColor : Color.secondary)
        // Not ⌘⌥Z: any "z" key equivalent outside the Edit menu trips the
        // ⌘Z single-owner guard (#4354).
        .help("Show or Hide Zoom Controls (⌘⌥E)")
        .keyboardShortcut("e", modifiers: [.command, .option])
        .accessibilityLabel("Show or hide zoom controls")
        .accessibilityIdentifier("previewHeadZoomControlsToggle")
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
            .help("Which rendition of this page is showing — original, enhanced, deskewed…")
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

    /// Coding v1 (Daniel, 2026-08-30, ruling 4): the chevron menu's "Tag Next
    /// Highlight…" opens this popover; its comma-separated tags ride the next
    /// saved highlight / underline / strikethrough / check.
    @State private var showTagPopover = false

    // Order ruled 2026-08-31 (Daniel): the three SELECTION tools first —
    // text, rectangular, words — then Draw Region, then the marks that put
    // something on the page (line, highlight, note, star, check), then the
    // edit verbs. Selecting comes before marking because you pick what you
    // are about to mark.
    var body: some View {
        toolButton(
            icon: PreviewMarkupTool.textSelect.icon,
            label: PreviewMarkupTool.textSelect.label,
            identifier: "previewMarkupTextSelect",
            key: "t",
            help: "Select Text — drag over recognised text to select it (⌘⌥T)",
            mode: .textSelect
        ) {
            NotificationCenter.default.post(
                name: .previewAnnotateTool, object: PreviewMarkupTool.textSelect.rawValue
            )
        }

        toolButton(
            icon: PreviewMarkupTool.select.icon,
            label: PreviewMarkupTool.select.label,
            identifier: "previewMarkupSelect",
            key: "v",
            help: "Select — click or ⇧-click regions to select, drag to move them (⌘⌥V)",
            mode: .select
        ) {
            NotificationCenter.default.post(
                name: .previewRegionVerb, object: PreviewRegionVerb.select.rawValue
            )
        }

        toolButton(
            icon: PreviewMarkupTool.wordSelect.icon,
            label: PreviewMarkupTool.wordSelect.label,
            identifier: "previewMarkupWordSelect",
            key: "w",
            // Daniel, 2026-08-31: "select words is really rectangular
            // selection…" — it IS a marquee, but what it comes away holding
            // is WORDS, so the tooltip says so rather than leaving the two
            // rectangular tools indistinguishable.
            help: "Select Words — marquee a rectangle; the recognised WORD boxes it touches "
                + "become the selection, which Highlight and Check then act on (⌘⌥W)",
            mode: .wordSelect
        ) {
            // Sticky mode only — the canvas selects word boxes while armed.
        }

        toolButton(
            icon: PreviewMarkupTool.drawRegion.icon,
            label: PreviewMarkupTool.drawRegion.label,
            identifier: "previewMarkupDrawRegion",
            key: "r",
            help: "Draw Region — drag a box to make a new region on this page (⌘⌥R)",
            mode: .drawRegion
        ) {
            NotificationCenter.default.post(
                name: .previewRegionVerb, object: PreviewRegionVerb.draw.rawValue
            )
        }

        toolButton(
            icon: PreviewMarkupTool.line.icon,
            label: PreviewMarkupTool.line.label,
            identifier: "previewMarkupLine",
            // ⌘⌥D ("draw a line"): ⌘⌥L is the Loupe toggle on this same
            // surface (ImagePreviewMenuCommands), and SwiftUI lets duplicate
            // shortcuts collide silently.
            key: "d",
            help: "Line — drag to draw a line on the page (⌘⌥D)",
            mode: .line
        ) {
            NotificationCenter.default.post(
                name: .previewAnnotateTool, object: PreviewMarkupTool.line.rawValue
            )
        }

        labeled(PreviewMarkupTool.highlight.label) { highlightSplitButton }

        noteButton

        toolButton(
            icon: PreviewMarkupTool.star.icon,
            label: PreviewMarkupTool.star.label,
            identifier: "previewMarkupStar",
            key: "s",
            help: "Star — drag a box to star that place on the page (⌘⌥S)"
        ) {
            NotificationCenter.default.post(
                name: .previewAnnotateTool, object: PreviewMarkupTool.star.rawValue
            )
        }

        toolButton(
            icon: PreviewMarkupTool.check.icon,
            label: PreviewMarkupTool.check.label,
            identifier: "previewMarkupCheck",
            key: "k",
            help: "Check — with words selected, checks THEM; otherwise click by a line to mark "
                + "it with one check, again for two, again for three, again to clear (⌘⌥K)",
            mode: .check
        ) {
            // Ruling 4 (Daniel, 2026-08-31): a check should land on the text
            // you already picked. The canvas answers this by checking the
            // selection when there is one, and staying armed for a click
            // when there is not — so the button posts either way.
            NotificationCenter.default.post(
                name: .previewAnnotateTool, object: PreviewMarkupTool.check.rawValue
            )
        }

        editVerbs
    }

    /// Delete / Combine act on the SELECTED bounding boxes (Daniel,
    /// 2026-08-31, ruling 2), so they are only shown while there IS a
    /// selection — a destructive verb with nothing to destroy is the bar
    /// lying about what a press would do. `RegionSelection` is `@Observable`,
    /// so reading it here re-renders the row as the selection comes and goes.
    @ViewBuilder
    private var editVerbs: some View {
        let selection = RegionSelection.shared
        if !selection.isEmpty {
            Divider().frame(height: PaneHeadMetrics.dividerHeight)

            // No ⌘⌥ binding: Delete already answers to the ⌫ key path the
            // canvas owns, and a second binding for the destructive verb is
            // how you get two code paths that drift.
            toolButton(
                icon: "trash",
                label: selection.count == 1 ? "Delete" : "Delete \(selection.count)",
                identifier: "previewMarkupDelete",
                help: "Delete — remove the selected regions or marks (⌫)"
            ) {
                NotificationCenter.default.post(
                    name: .previewRegionVerb, object: PreviewRegionVerb.delete.rawValue
                )
            }

            // Combine needs two boxes to have anything to merge.
            if selection.count >= 2 {
                toolButton(
                    icon: "arrow.triangle.merge",
                    label: "Combine \(selection.count)",
                    identifier: "previewMarkupCombine",
                    key: "c", help: "Combine — merge the selected regions into one (⌘⌥C)"
                ) {
                    NotificationCenter.default.post(
                        name: .previewRegionVerb, object: PreviewRegionVerb.combine.rawValue
                    )
                }
            }
        }
    }

    /// Text Note (Daniel, 2026-08-31: "text note doesn't work"). Arming the
    /// tool and dragging a box saves a note-kind annotation; the canvas then
    /// opens `InlineNoteEditor` AT the anchor (Daniel, 2026-09-04: notes are
    /// typed in place like a margin note, not in a popover off this bar —
    /// the popover that used to hang here moved onto the page).
    @ViewBuilder
    private var noteButton: some View {
        toolButton(
            icon: PreviewMarkupTool.note.icon,
            label: PreviewMarkupTool.note.label,
            identifier: "previewMarkupNote",
            key: "n",
            help: "Text Note — drag a box, then type the note that belongs there (⌘⌥N)",
            mode: .note
        ) {
            NotificationCenter.default.post(
                name: .previewAnnotateTool, object: PreviewMarkupTool.note.rawValue
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
            .keyboardShortcut("h", modifiers: [.command, .option])
            .help("Highlight — drag over words to highlight them in \(highlightStyle.label) (⌘⌥H)")
            .accessibilityLabel("Highlight, \(highlightStyle.label)")
            .accessibilityIdentifier("previewMarkupHighlight")

            Menu {
                ForEach(PreviewHighlightStyle.colors) { style in
                    styleRow(style)
                }
                Divider()
                styleRow(.underline)
                styleRow(.strikethrough)
                Divider()
                MarkupTagMenuEntries(showTagPopover: $showTagPopover)
            } label: {
                Image(systemName: "chevron.down")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .menuStyle(.borderlessButton)
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Highlight color and mode — pick a color, or underline/strikethrough instead")
            .accessibilityLabel("Highlight color and mode")
            .accessibilityIdentifier("previewMarkupHighlightMenu")
        }
        .popover(isPresented: $showTagPopover) { MarkupTagPopover() }
    }

    private func styleRow(_ style: PreviewHighlightStyle) -> some View {
        PreviewHighlightStyleMenu.styleRow(
            style, current: highlightStyle
        ) { highlightStyleRaw = $0.rawValue }
    }

    /// ⌘⌥ + mnemonic for every tool (Daniel, 2026-08-31). Not bare letters —
    /// those would steal typing from any text field on the surface — and not
    /// ⌃, which collides with the emacs-style editing bindings AppKit gives
    /// every text view for free.
    private func toolButton(
        icon: String, label: String, identifier: String,
        key: KeyEquivalent? = nil, help: String,
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
            .keyboardShortcut(key.map { KeyboardShortcut($0, modifiers: [.command, .option]) })
            .help(help)
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

    @State private var showTagPopover = false

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
            Divider()
            MarkupTagMenuEntries(showTagPopover: $showTagPopover)
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
        .popover(isPresented: $showTagPopover) { MarkupTagPopover() }
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

// The tag-entry structs (`MarkupTagMenuEntries` / `MarkupTagPopover`, coding
// v1, ruling 4) live in AnnotationBar.swift — the annotation bar is the one
// home for markup verbs; both chevron menus here mount them.

