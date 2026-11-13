import SwiftUI

// The shape tools, one top-level toggle each (owner 2026-11-10: the ▾ menu hid them).
extension PreviewMarkupToolsRow {
    /// What the ONE Shape tool draws while editing segments (`source.editor.draw-shapes`): Region (drag a box),
    /// Polygon (click points; click the first, or double-click, to close), Line (a baseline: click points,
    /// double-click to finish). Choosing one arms the tool; choosing the armed one puts it down.
    var shapeButtons: some View {
        Group {
            shapeButton(.box, label: "Region", icon: "rectangle.dashed", key: "r",
                        help: "Region — drag a box (⌘⌥R)")
            shapeButton(.polygon, label: "Polygon", icon: "pentagon", key: nil,
                        help: "Polygon — click points; the first point or a double-click closes it")
            shapeButton(.baseline, label: "Line", icon: "line.diagonal", key: nil,
                        help: "Line — click points along the text, double-click to finish")
            knifeButton
        }
    }

    /// The Knife (`segment-editor.split-knife`): drag across lines to cut each where the stroke crosses its baseline.
    /// Chosen, it stays until another tool is chosen; holding K gives it for one stroke.
    private var knifeButton: some View {
        let armed = windowState?.knifeArmed == true
        return labeled("Knife") {
            Button {
                if !armed { windowState?.activeMarkupTool = .select }
                windowState?.knifeArmed = !armed
            } label: {
                Image(systemName: "scissors")
            }
            .buttonStyle(.borderless)
            .foregroundStyle(armed ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary))
            .help("Knife — drag across lines to cut them where the stroke crosses (hold K for one stroke)")
            .accessibilityLabel("Knife")
            .accessibilityIdentifier("segmentEditor.tool.knife")
        }
    }

    private func shapeButton(
        _ kind: SegmentShapes.DrawKind, label: String, icon: String, key: KeyEquivalent?, help: String
    ) -> some View {
        let armed = windowState?.activeMarkupTool == .drawRegion && windowState?.shapeKind == kind
        return labeled(label) {
            Button {
                if armed { windowState?.activeMarkupTool = nil; return }
                windowState?.knifeArmed = false
                windowState?.shapeKind = kind
                windowState?.activeMarkupTool = .drawRegion
                NotificationCenter.default.post(name: .previewRegionVerb, object: PreviewRegionVerb.draw.rawValue)
            } label: {
                Image(systemName: icon)
            }
            .buttonStyle(.borderless)
            .foregroundStyle(armed ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary))
            .keyboardShortcut(key.map { KeyboardShortcut($0, modifiers: [.command, .option]) })
            .help(help)
            .accessibilityLabel(label)
            .accessibilityIdentifier("previewMarkupShape\(kind.title)")
        }
    }
}

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
