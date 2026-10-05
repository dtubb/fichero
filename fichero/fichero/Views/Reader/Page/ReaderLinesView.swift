import FicheroAPIClient
import SwiftUI

/// The Reader's Lines mode (#5414, `reader.lines.image-above-text`): down the page, each line's picture
/// cut from the source above its reading, editable in place. The working pass's lines in the engine's
/// order (`ReaderLines.lines`). It follows the focused Preview's selection as the other Reader modes do,
/// and a click on a line's picture reveals it there (#5424's one reveal, as the Reader's line click).
/// Zoom is the Reader's own (`webZoom`): the pane's zoom buttons and ⌘+/⌘− scale picture and words.
struct ReaderLinesView: View {
    let documentId: String
    let zoom: Double

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(WindowState.self) private var windowState: WindowState?

    var body: some View {
        if let segmentService {
            content(SegmentStore.shared(for: segmentService))
                .task(id: documentId) { await SegmentStore.shared(for: segmentService).load(documentId: documentId) }
        } else {
            PaneEmptyStateView(reason: "This window cannot read a page's lines.")
        }
    }

    @ViewBuilder
    private func content(_ store: SegmentStore) -> some View {
        let lines = ReaderLines.lines(documentId: documentId, store: store)
        if lines.isEmpty {
            PaneEmptyStateView(
                reason: store.isLoading(documentId: documentId)
                    ? "Reading the page's lines…" : "This page has no lines yet. Find lines on it first.",
                systemImage: "text.below.photo"
            )
        } else {
            let direction = store.directionResolver(documentId: documentId)
            let shown = ReaderLines.shown(selectedIds(store), among: lines, segments: store.segments(documentId: documentId))
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 12) {
                        ForEach(lines) { line in
                            ReaderLineRow(
                                segment: line, direction: direction(line.id), zoom: zoom,
                                isSelected: shown.contains(line.id),
                                onPick: { reveal(line.id, store: store) }
                            )
                            .id(line.id)
                        }
                    }
                    .padding(12)
                }
                .onChange(of: shown) { _, now in
                    guard let first = lines.first(where: { now.contains($0.id) }) else { return }
                    withAnimation { proxy.scrollTo(first.id, anchor: .center) }
                }
            }
        }
    }

    /// The focused Preview's selection on this page, as segment ids -- the Inspector's one resolution.
    private func selectedIds(_ store: SegmentStore) -> [String] {
        guard let selection = windowState?.focusedRegionSelection else { return [] }
        return InspectorPath.selectedSegmentIds(selection: selection, documentId: documentId, store: store)
    }

    private func reveal(_ segmentId: String, store: SegmentStore) {
        windowState?.revealSegments([segmentId], documentId: documentId, store: store)
    }
}

/// ONE line: its picture, and below it (beside it, for a vertical line) its reading, editable in place.
/// The Lines mode's row and the Preview's double-click popover are this view (#5414).
struct ReaderLineRow: View {
    let segment: Segment
    /// The line's resolved direction (the engine's cascade); nil reads as written across.
    let direction: String?
    let zoom: Double
    var isSelected = false
    /// A click on the picture; nil when there is nothing to reveal (the popover sits on the line already).
    var onPick: (() -> Void)?

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @Environment(ActionStore.self) private var actionStore: ActionStore?
    @Environment(\.undoManager) private var undoManager
    @State private var editor: ReaderLineEditor

    init(segment: Segment, direction: String?, zoom: Double, isSelected: Bool = false, onPick: (() -> Void)? = nil) {
        self.segment = segment
        self.direction = direction
        self.zoom = zoom
        self.isSelected = isSelected
        self.onPick = onPick
        _editor = State(initialValue: ReaderLineEditor(segment: segment))
    }

    private var metrics: ReaderLines.Metrics { ReaderLines.Metrics(zoom: zoom) }

    var body: some View {
        Group {
            switch ReaderLines.arrangement(direction: direction) {
            case .above:
                VStack(alignment: .leading, spacing: 6) {
                    ScrollView(.horizontal) { picture }
                    words
                }
            case .beside:
                HStack(alignment: .top, spacing: 8) {
                    picture
                    words
                }
            }
        }
        .padding(8)
        .background(isSelected ? Color.accentColor.opacity(0.14) : .clear, in: RoundedRectangle(cornerRadius: 6))
        .task(id: segment.id) {
            if let segmentService { await editor.load(segmentService) }
        }
    }

    /// The line's picture at `metrics.pictureExtent` across the line, always larger than its words.
    @ViewBuilder
    private var picture: some View {
        let extent = metrics.pictureExtent
        let vertical = ReaderLines.arrangement(direction: direction) == .beside
        Button { onPick?() } label: {
            Group {
                if let image = editor.picture {
                    Image(platformImage: image).resizable().scaledToFit()
                } else {
                    Rectangle().fill(.quaternary)
                        .overlay { Image(systemName: "photo").foregroundStyle(.secondary) }
                        .frame(width: vertical ? extent : extent * 6, height: vertical ? extent * 6 : extent)
                }
            }
            .frame(width: vertical ? extent : nil, height: vertical ? nil : extent)
            .clipShape(RoundedRectangle(cornerRadius: 3))
        }
        .buttonStyle(.plain)
        .disabled(onPick == nil)
        .accessibilityLabel("Picture of the line")
        .help(onPick == nil ? "" : "Show this line in the Preview")
    }

    private var words: some View {
        VStack(alignment: .leading, spacing: 4) {
            field
            if editor.isChanged {
                HStack {
                    Spacer()
                    Button("Revert", role: .cancel) { editor.revert() }
                    Button("Save") { Task { await save() } }
                }
                .font(.caption)
            }
            if let note = editor.note {
                Text(note).font(.caption).foregroundStyle(.secondary)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    @ViewBuilder
    private var field: some View {
        switch InspectorReadingEdit.layout(direction: direction) {
        case .vertical:
            #if os(macOS)
            VerticalTextEditor(text: $editor.draft, pointSize: metrics.fontSize)
                .frame(minWidth: metrics.fontSize * 2, maxWidth: .infinity, minHeight: metrics.pictureExtent * 4)
                .accessibilityLabel("Reading, top to bottom")
            #else
            horizontalField(rightToLeft: false)
            #endif
        case .horizontal(let rightToLeft):
            horizontalField(rightToLeft: rightToLeft)
        }
    }

    private func horizontalField(rightToLeft: Bool) -> some View {
        TextField("Reading", text: $editor.draft, axis: .vertical)
            .font(BundledFonts.shared.font(size: metrics.fontSize))
            .multilineTextAlignment(rightToLeft ? .trailing : .leading)
            .environment(\.layoutDirection, rightToLeft ? .rightToLeft : .leftToRight)
            .textFieldStyle(.plain)
            .lineLimit(1...6)
            .onSubmit { Task { await save() } }
            .accessibilityLabel("Reading of the line")
    }

    /// The Inspector's own save (`InspectorReadingEdit.save` through `ReaderTextEditRunner`).
    private func save() async {
        guard editor.isChanged, let segmentService, let actionsService = actionStore?.actionsService else { return }
        let runner = ReaderTextEditRunner(
            actionsService: actionsService, segmentService: segmentService, undoManager: undoManager,
            refreshPage: { _ in }
        )
        await editor.save(runner: runner, service: segmentService)
    }
}

/// The Preview's double-click popover (`preview.segment.double-click-popover`): the segment's picture
/// large, its reading below, editable -- one row of the Lines mode, the same view.
struct ReaderLinePopover: View {
    let segmentId: String
    let documentId: String

    @Environment(SegmentService.self) private var segmentService: SegmentService?

    var body: some View {
        Group {
            if let segmentService, let row = Self.row(segmentId: segmentId, documentId: documentId,
                                                       store: SegmentStore.shared(for: segmentService)) {
                row
            } else {
                Text("This segment cannot be read here.").font(.callout).foregroundStyle(.secondary).padding()
            }
        }
        .frame(minWidth: 320, idealWidth: 520, maxWidth: 720)
    }

    /// The row the popover shows: the Lines mode's row for that segment, at the popover's zoom.
    @MainActor
    static func row(segmentId: String, documentId: String, store: SegmentStore) -> ReaderLineRow? {
        guard let segment = store.segments(documentId: documentId).first(where: { $0.id == segmentId }) else { return nil }
        return ReaderLineRow(
            segment: segment, direction: store.direction(of: segmentId, documentId: documentId),
            zoom: ReaderLines.popoverZoom
        )
    }
}

#if DEBUG
#Preview("Lines: a Syriac line and a vertical Chinese line") {
    let anchor = SourceAnchorValue(generated: Components.Schemas.SourceAnchorOutput(documentId: "p1"))
    let syriac = Segment(
        id: "l1", provisional: false, documentId: "p1", passId: "p", kind: "line", kindRaw: nil,
        parentSegmentId: nil, provenanceKind: .externalImport, anchor: anchor, baseline: nil,
        text: "ܐܒܪܗܡ ܐܘܠܕ ܠܐܝܣܚܩ", confidence: nil, sourceArtifactId: nil, boxIndex: 0, pageIndex: nil, metadata: nil
    )
    var chinese = syriac
    chinese.id = "l2"
    chinese.text = "登庸九年"
    return VStack(alignment: .leading, spacing: 12) {
        ReaderLineRow(segment: syriac, direction: "rtl", zoom: 1.2, isSelected: true)
        ReaderLineRow(segment: chinese, direction: "ttb", zoom: 1.2)
    }
    .padding()
    .frame(width: 480)
}
#endif
