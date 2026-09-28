import SwiftUI

/// The Inspector at the selection's LEVEL (ruled 2026-09-27, `build-notes-inspector.md`): a path head
/// -- Page › block › line › word, where clicking a crumb inspects that level -- then the same sections
/// at every level, a section with nothing to say hidden. Slice 1 has two: Text and Order.
///
/// The Inspector never types a reading or draws a shape; its verbs act on the selection (ruled).
/// It has no selection of its own: it shows the focused pane's.
struct SegmentInspectorView: View {
    let documentId: String
    /// The focused pane's selection, as segment ids, in the order picked.
    let selectedIds: [String]

    @Environment(SegmentService.self) private var segmentService: SegmentService?
    @State private var level: Level = .selection
    @State private var text: InspectorText?

    /// What the sections describe: the selection itself, a crumb the person clicked, or the page.
    enum Level: Equatable {
        case selection
        case segment(String)
        case page
    }

    private var segments: [Segment] {
        segmentService.map { SegmentStore.shared(for: $0).segments(documentId: documentId) } ?? []
    }

    private var path: InspectorPath? {
        selectedIds.count == 1
            ? InspectorPath.to(selectedIds[0], in: segments)
            : InspectorPath.common(selectedIds, in: segments)
    }

    /// The inspected segment; nil is the page. A mixed selection is inspected at its common parent.
    private var inspected: String? {
        switch level {
        case .page: nil
        case .segment(let id): id
        case .selection: selectedIds.count == 1 ? selectedIds.first : path?.crumbs.last?.segmentId
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            pathHead
                .padding(.horizontal, 8)
                .padding(.vertical, 6)
            Divider()
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if selectedIds.count > 1, level == .selection {
                        Text(countsLine).font(.caption).foregroundStyle(.secondary)
                    }
                    if let text, !text.readings.isEmpty {
                        InspectorTextSection(text: text)
                    }
                    if level == .page {
                        // Page level: how the page's passes were made (#5149).
                        InspectorMakingSection(documentId: documentId)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .padding(8)
            }
            // The Order section: the inspected segment's children, rearrangeable with the same verbs
            // as everywhere else (one `ReadingOrderStore`); hidden when it has none.
            ReadingOrderList(documentId: documentId, parentSegmentId: inspected, hidesWhenEmpty: true)
                .frame(maxHeight: 260)
        }
        .task(id: inspected) {
            text = nil
            guard let inspected, let segmentService else { return }
            text = try? await segmentService.readings(segmentId: inspected)
        }
        .onChange(of: selectedIds) { level = .selection }
    }

    private var pathHead: some View {
        HStack(spacing: 4) {
            crumb("Page", selected: inspected == nil) { level = .page }
            ForEach(path?.crumbs ?? []) { crumb in
                Image(systemName: "chevron.right").font(.caption2).foregroundStyle(.tertiary)
                self.crumb(crumb.label, selected: inspected == crumb.segmentId) { level = .segment(crumb.segmentId) }
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Path")
    }

    private func crumb(_ title: String, selected: Bool, action: @escaping () -> Void) -> some View {
        Button(title, action: action)
            .buttonStyle(.borderless)
            .font(selected ? .caption.weight(.semibold) : .caption)
            .foregroundStyle(selected ? .primary : .secondary)
    }

    private var countsLine: String {
        InspectorPath.kindCounts(selectedIds, in: segments)
            .map { "\($0.count) \($0.count == 1 ? $0.kind : $0.kind + "s")" }
            .joined(separator: ", ")
    }
}

/// Every live reading, grouped by kind; the one that counts is marked with WHY it counts.
struct InspectorTextSection: View {
    let text: InspectorText

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Text").font(.headline)
            ForEach(text.kinds, id: \.self) { kind in
                VStack(alignment: .leading, spacing: 6) {
                    Text(kind.capitalized).font(.subheadline).foregroundStyle(.secondary)
                    ForEach(text.readings(ofKind: kind)) { reading in
                        row(reading)
                    }
                    if let counting = text.counting[kind], counting.readingId == nil {
                        Text(counting.why.label).font(.caption).foregroundStyle(.secondary)
                    }
                }
            }
        }
    }

    private func row(_ reading: InspectorText.Reading) -> some View {
        let counts = text.counts(reading)
        return VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                Image(systemName: counts ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(counts ? Color.accentColor : .secondary)
                    .accessibilityLabel(counts ? "Counts" : "Does not count")
                if let role = reading.pairRole {
                    Text(role).font(.caption.monospaced()).foregroundStyle(.secondary)
                }
                Text(reading.content).font(.body).textSelection(.enabled)
            }
            Text(detail(reading, counts: counts)).font(.caption).foregroundStyle(.secondary)
        }
    }

    /// Who made it, who wrote it down, the guideline, and -- for the one that counts -- why.
    private func detail(_ reading: InspectorText.Reading, counts: Bool) -> String {
        var parts = [reading.maker.capitalized]
        if let author = reading.author { parts.append(author) }
        if let guideline = reading.guideline { parts.append(guideline) }
        if counts, let why = text.counting[reading.kind]?.why { parts.append(why.label) }
        return parts.joined(separator: " · ")
    }
}

#if DEBUG
#Preview("Text: a machine reading, a person's correction that counts, a sic / corr pair") {
    let reading = { (id: String, content: String, maker: String, pair: String?, role: String?) in
        InspectorText.Reading(
            id: id, kind: "transcription", content: content, maker: maker, author: maker == "human" ? "dtubb" : nil,
            guideline: "diplomatic", pairId: pair, pairRole: role
        )
    }
    InspectorTextSection(text: InspectorText(
        readings: [
            reading("r1", "Tlie qnick brown fox", "workflow", nil, nil),
            reading("r2", "The quick brown fox", "human", nil, nil),
            reading("r3", "recieve", "human", "p1", "sic"),
            reading("r4", "receive", "human", "p1", "corr")
        ],
        counting: ["transcription": .init(readingId: "r2", why: .chosen)]
    ))
    .padding()
    .frame(width: 320)
}
#endif
