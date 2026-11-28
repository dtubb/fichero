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
            lineShapeButton
            levelPicker
            knifeButton
            markerButton
            orderButton
            brushButton
            paintButton
            labeled("Simplify") { SimplifySliderButton(windowState: windowState) }
        }
    }

    /// The Line tool (#7083, ⌘⌥⇧L): draws a line as a polygon (click points) or as a box (drag from the first point,
    /// `SegmentShapes.firstPointStartsBox`) in the region that holds it.
    private var lineShapeButton: some View {
        let armed = windowState?.activeMarkupTool == .drawRegion && windowState?.drawnLevel == .line
        return labeled("New Line") {
            Button {
                if armed { windowState?.activeMarkupTool = nil; return }
                windowState?.armDraw(.line)
            } label: {
                Image(systemName: "text.alignleft")
            }
            .buttonStyle(.borderless)
            .foregroundStyle(armed ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary))
            .keyboardShortcut("l", modifiers: [.command, .option, .shift])
            .help("New Line — click the corners of a line of writing, or drag a box; it goes into the region that holds it (⌘⌥⇧L)")
            .accessibilityLabel("New Line")
            .accessibilityIdentifier("segmentEditor.tool.newLine")
        }
    }

    /// What the polygon and rectangle tools make (#7083): Region, Line or Word, kept; Follow Selection draws a line in a
    /// selected region and a word in a selected line.
    private var levelPicker: some View {
        labeled("Makes") {
            Picker("Makes", selection: Binding(get: { windowState?.drawnLevel }, set: { windowState?.drawnLevel = $0 })) {
                Text("Follow Selection").tag(SegmentShapes.DrawnLevel?.none)
                ForEach(SegmentShapes.DrawnLevel.allCases) { level in Text(level.title).tag(SegmentShapes.DrawnLevel?.some(level)) }
            }
            .pickerStyle(.menu)
            .labelsHidden()
            .fixedSize()
            .help("What the polygon and rectangle tools make: a region, a line or a word; or follow the selection")
            .accessibilityIdentifier("segmentEditor.tool.drawLevel")
        }
    }

    /// The Knife (`segment-editor.split-knife`): drag across lines to cut each where the stroke crosses its baseline.
    /// Chosen, it stays until another tool is chosen; holding K gives it for one stroke.
    private var knifeButton: some View {
        let armed = windowState?.knifeArmed == true
        return labeled("Knife") {
            Button {
                windowState?.chooseSegmentTool(armed ? nil : .knife)
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

    /// The Marker (`segment-editor.marker`): draw freehand; a stroke that closes on itself is an outline, any other a
    /// baseline. Chosen, it stays until another tool is chosen; holding M gives it for one stroke.
    private var markerButton: some View {
        let armed = windowState?.markerArmed == true
        return labeled("Marker") {
            Button {
                windowState?.chooseSegmentTool(armed ? nil : .marker)
            } label: {
                Image(systemName: "pencil.tip")
            }
            .buttonStyle(.borderless)
            .foregroundStyle(armed ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary))
            .help("Marker — draw freehand: close the stroke for an outline, leave it open for a baseline (hold M for one stroke)")
            .accessibilityLabel("Marker")
            .accessibilityIdentifier("segmentEditor.tool.marker")
        }
    }

    /// Order (`segment-editor.order-by-clicking`): click segments in turn to number them; choosing it again (or O,
    /// Return, Esc, another tool) sets the order, one undo.
    private var orderButton: some View {
        let armed = windowState?.orderArmed == true
        return labeled("Order") {
            Button {
                windowState?.chooseSegmentTool(armed ? nil : .order)
            } label: {
                Image(systemName: "list.number")
            }
            .buttonStyle(.borderless)
            .foregroundStyle(armed ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary))
            .help("Order — click segments in the order they are read (O); choose it again to set the order")
            .accessibilityLabel("Order")
            .accessibilityIdentifier("segmentEditor.tool.order")
        }
    }

    /// The Brush (`segment-editor.select-brush`): paint over segments to select them (⌥ takes away, `[` `]` size). Chosen,
    /// it stays until another tool is chosen; holding B gives it for one stroke.
    private var brushButton: some View {
        let armed = windowState?.brushArmed == true
        return labeled("Select Brush") {
            Button {
                windowState?.chooseSegmentTool(armed ? nil : .brush)
            } label: {
                Image(systemName: "paintbrush.pointed")
            }
            .buttonStyle(.borderless)
            .foregroundStyle(armed ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary))
            .help("Select Brush — brush over segments to select them; ⌥ takes away, [ and ] change the size (hold B for one stroke)")
            .accessibilityLabel("Select Brush")
            .accessibilityIdentifier("segmentEditor.tool.brush")
        }
    }

    /// The Paintbrush (`segment-editor.paintbrush`): paint along a line of ink to make it a line (P; `[` `]` width).
    private var paintButton: some View {
        let armed = windowState?.paintArmed == true
        return labeled("Line Brush") {
            Button {
                windowState?.chooseSegmentTool(armed ? nil : .paint)
            } label: {
                Image(systemName: "paintbrush")
            }
            .buttonStyle(.borderless)
            .foregroundStyle(armed ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.secondary))
            .help("Line Brush — paint along a line of writing to make a line (P); [ and ] change the width")
            .accessibilityLabel("Line Brush")
            .accessibilityIdentifier("segmentEditor.tool.paintbrush")
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
                windowState?.markerArmed = false
                windowState?.orderArmed = false
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

/// Simplify's popover (`segment-editor.vertices`): a slider in image pixels. While it is held the page shows what the
/// engine would make of the selection; let go, ONE `segment.simplify` at that tolerance, one ⌘Z.
extension PreviewMarkupToolsRow { struct SimplifySliderButton: View {
    let windowState: WindowState?
    @State private var showing = false
    @State private var tolerance = SegmentEdit.simplifyTolerance

    var body: some View {
        Button { showing.toggle() } label: { Image(systemName: "point.3.connected.trianglepath.dotted") }
            .buttonStyle(.borderless)
            .foregroundStyle(.secondary)
            .help("Simplify — fewer points on the selected outlines and baselines")
            .accessibilityLabel("Simplify")
            .accessibilityIdentifier("segmentEditor.tool.simplify")
            .popover(isPresented: $showing) {
                VStack(alignment: .leading, spacing: 6) {
                    Text("Simplify the selection").font(.headline)
                    Slider(value: $tolerance, in: 0.5...20) { editing in
                        if editing {
                            windowState?.simplifyTolerance = tolerance
                        } else {
                            windowState?.letGoOfSimplifySlider(at: tolerance)
                        }
                    }
                    .onChange(of: tolerance) { _, value in
                        if windowState?.simplifyTolerance != nil { windowState?.simplifyTolerance = value }
                    }
                    .accessibilityIdentifier("segmentEditor.simplify.slider")
                    Text("Within \(tolerance, specifier: "%.1f") px of the shape drawn")
                        .font(.caption).foregroundStyle(.secondary)
                }
                .padding()
                .frame(width: 240)
            }
    }
} }

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
