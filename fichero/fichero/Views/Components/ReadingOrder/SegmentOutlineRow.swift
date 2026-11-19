import SwiftUI

/// One row of the nested Segments list (hierarchy A, #5426, `source.editor.hierarchy.segments-list-nests`): the
/// swatch of the colour its box is drawn in (`SelectionStyle.regionSwatch`, the one colour path), its words, and
/// its children disclosed under it, indented -- a region open on its lines, a line closed on its
/// words.
struct SegmentOutlineRow: View {
    let node: SegmentsPane.OutlineRow
    let index: Int
    let tones: [String: RegionColours.Tone]
    /// The list's own row for an id (its words, its flag).
    let content: (String, Int) -> AnyView
    /// What surrounds the whole row (the swatch included): the list's drag and drop, lit across the row.
    let wrap: (String, AnyView) -> AnyView
    /// The row lit as a drop target: the WHOLE row's background (the list row), not the words' width.
    var lit: String?
    /// Every group open, as while a filter is on: a match must never sit inside a closed group (#6476).
    var opensAll = false

    @State private var expanded: Bool

    init(
        node: SegmentsPane.OutlineRow, index: Int, tones: [String: RegionColours.Tone],
        content: @escaping (String, Int) -> AnyView, wrap: @escaping (String, AnyView) -> AnyView = { _, view in view },
        lit: String? = nil, opensAll: Bool = false
    ) {
        self.wrap = wrap
        self.lit = lit
        self.opensAll = opensAll
        self.node = node
        self.index = index
        self.tones = tones
        self.content = content
        // A region shows its lines; a line keeps its words until asked.
        _expanded = State(initialValue: SegmentHierarchy.Level(kind: node.kind) == .region)
    }

    var body: some View {
        Group { rows }
            // The drop target's whole row, edge to edge, like the sidebar's.
            .listRowBackground(lit == node.segmentId ? Color.accentColor.opacity(0.25) : Color.clear)
    }

    @ViewBuilder private var rows: some View {
        if node.children.isEmpty {
            labelled
        } else {
            DisclosureGroup(isExpanded: opensAll ? .constant(true) : $expanded) {
                ForEach(Array(node.children.enumerated()), id: \.element.id) { position, child in
                    SegmentOutlineRow(
                        node: child, index: position, tones: tones, content: content, wrap: wrap, lit: lit, opensAll: opensAll
                    )
                }
            } label: {
                labelled
            }
        }
    }

    private var labelled: some View {
        wrap(node.segmentId, AnyView(
            HStack(spacing: 6) {
                // The kind's icon in the hue its box is drawn in: the swatch and the kind in one mark.
                Image(systemName: SegmentHierarchy.Level(kind: node.kind).symbolName)
                    .foregroundStyle(SelectionStyle.regionSwatch(tones[node.segmentId]))
                    .frame(width: 16)
                    .accessibilityHidden(true)
                content(node.segmentId, index)
            }
        ))
        .tag(node.segmentId)
    }
}

#if DEBUG
#Preview("Nested: a region, its lines, a line's words") {
    let words = ["In", "the", "beginning"].map { SegmentsPane.OutlineRow(segmentId: $0, kind: "word", children: []) }
    let lines = (1...3).map {
        SegmentsPane.OutlineRow(segmentId: "line \($0)", kind: "line", children: $0 == 1 ? words : [])
    }
    let regions = [
        SegmentsPane.OutlineRow(segmentId: "body", kind: "region", children: lines),
        SegmentsPane.OutlineRow(segmentId: "marginal note", kind: "region", children: [])
    ]
    // The region at full strength, its lines shaded along the order, the first line's words in its shade.
    let tones: [String: RegionColours.Tone] = [
        "body": .init(hue: 0, strength: 1), "marginal note": .init(hue: 1, strength: 1),
        "line 1": .init(hue: 0, strength: 1), "line 2": .init(hue: 0, strength: 0.725),
        "line 3": .init(hue: 0, strength: 0.45),
        "In": .init(hue: 0, strength: 1), "the": .init(hue: 0, strength: 1), "beginning": .init(hue: 0, strength: 1)
    ]
    return List {
        ForEach(Array(regions.enumerated()), id: \.element.id) { index, region in
            SegmentOutlineRow(node: region, index: index, tones: tones, content: { id, _ in AnyView(Text(id)) })
        }
    }
    .frame(width: 320, height: 300)
}

#endif
