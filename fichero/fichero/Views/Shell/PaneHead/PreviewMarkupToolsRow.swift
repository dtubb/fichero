import SwiftUI

//  Extracted for file_length (#5113) with that issue's checklist: path asserted free, cut
//  above the declaration's attributes and doc comment, no file-scope conditional-compilation
//  blocks and no file-scope `private` to strand, imports copied from the source verbatim.

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
            // Menu audit 2026-09-17: ⌘⌥T is the system Show/Hide Toolbar chord
            // (AppKit's own `.toolbar` group is present in this app), so the
            // old ⌘⌥T here raced it. "u" is free (MenuShortcutUniquenessTests'
            // denylist).
            key: "u",
            help: "Select Text — drag over recognised text to select it (⌘⌥U)",
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
            // Was ⌘⌥D ("draw a line"), chosen only to avoid ⌘⌥L (the Loupe
            // toggle on this same surface). Menu audit 2026-09-17: ⌘⌥D is
            // ITSELF a macOS system default ("Turn Dock Hiding On/Off"), a
            // second collision nobody had caught. "g" avoids both (still not
            // ⌘⌥L; see MenuShortcutUniquenessTests' denylist).
            key: "g",
            help: "Line — drag to draw a line on the page (⌘⌥G)",
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
        // Delete and Combine write segments, so they appear only in the segment-editing
        // mode (#5114); reading a page, a selection is for reading.
        if !selection.isEmpty, windowState?.isEditingSegments == true {
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
            // Menu audit 2026-09-17: ⌘⌥H is the system Hide Others chord —
            // rebound to ⌘⌥Y ("yellow", the default highlight color; free
            // per MenuShortcutUniquenessTests' denylist).
            .keyboardShortcut("y", modifiers: [.command, .option])
            .help("Highlight — drag over words to highlight them in \(highlightStyle.label) (⌘⌥Y)")
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

// Both label modes, as `AnnotationBar` shows them. No `WindowState` is injected: the row reads
// it optionally, so this is its no-window default (select tool, standard highlight style).
#Preview("Markup tools — icons") {
    PreviewMarkupToolsRow()
        .padding()
}

#Preview("Markup tools — with labels") {
    PreviewMarkupToolsRow(showsLabels: true)
        .padding()
}
