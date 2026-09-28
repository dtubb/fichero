import SwiftUI

/// The Segments pane's STRIP and GRID (`source.segments-pane.views`, #4942): the level's segments as
/// their pictures, cut from the page by the engine, with their words beneath, in the page's order
/// (the same `ReadingOrderStore` the list shows). A click selects, as a list row does; a double click
/// opens a segment that holds others.
struct SegmentsPictureGrid: View {
    let segmentIds: [String]
    let segments: [String: Segment]
    /// Strip: one row that scrolls sideways. Grid: rows that wrap.
    let isStrip: Bool
    let selected: String?
    let pick: (String) -> Void
    let open: (String) -> Void
    let opens: (String) -> Bool

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @State private var pictures: [String: PlatformImage] = [:]

    var body: some View {
        ScrollView(isStrip ? .horizontal : .vertical) {
            if isStrip {
                LazyHStack(alignment: .top, spacing: 8) { cells }.padding(8)
            } else {
                LazyVGrid(columns: [GridItem(.adaptive(minimum: 140), spacing: 8)], spacing: 8) { cells }.padding(8)
            }
        }
    }

    private var cells: some View {
        ForEach(Array(segmentIds.enumerated()), id: \.element) { index, id in
            cell(id, at: index)
        }
    }

    private func cell(_ id: String, at index: Int) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Group {
                if let image = pictures[id] {
                    Image(platformImage: image).resizable().scaledToFit()
                } else {
                    Rectangle().fill(.quaternary)
                        .overlay { Image(systemName: "photo").foregroundStyle(.secondary) }
                }
            }
            .frame(width: 140, height: 90)
            .clipShape(RoundedRectangle(cornerRadius: 4))
            Text(SegmentsPane.rowLabel(segments[id], at: index)).font(BundledFonts.shared.font(.caption)).lineLimit(2)
                .frame(width: 140, alignment: .leading)
            if opens(id) {
                Text("Double-click to open").font(.caption2).foregroundStyle(.tertiary)
            }
        }
        .padding(4)
        .background(selected == id ? Color.accentColor.opacity(0.2) : .clear, in: RoundedRectangle(cornerRadius: 6))
        .contentShape(Rectangle())
        .onTapGesture(count: 2) { if opens(id) { open(id) } }
        .onTapGesture { pick(id) }
        // A second route to Open, for touch (iPad has no double-click) and for the keyboard-less.
        .contextMenu {
            if opens(id) { Button("Open") { open(id) } }
        }
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(selected == id ? [.isButton, .isSelected] : .isButton)
        .task(id: id) { await load(id) }
    }

    private func load(_ id: String) async {
        guard pictures[id] == nil, let segmentService,
              let data = try? await SegmentPictureService(client: segmentService.client).picture(segmentId: id),
              let image = PlatformImage(data: data) else { return }
        pictures[id] = image
    }
}

#if DEBUG
#Preview("Segments grid — three regions, the first selected") {
    let ids = ["r1", "r2", "r3"]
    SegmentsPictureGrid(
        segmentIds: ids, segments: [:], isStrip: false, selected: "r1",
        pick: { _ in }, open: { _ in }, opens: { $0 == "r1" }
    )
    .frame(width: 480, height: 260)
}
#endif
