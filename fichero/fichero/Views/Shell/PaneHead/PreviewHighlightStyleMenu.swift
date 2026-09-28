import SwiftUI

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
