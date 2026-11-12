import SwiftUI

/// Language, script, direction and encoding for the inspected segment, each saying where it came from
/// (#5158). A fallback says it is one.
struct InspectorLanguageSection: View {
    let rows: [InspectorLanguage.Row]

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Language & Script").font(.headline)
            ForEach(rows) { row in
                VStack(alignment: .leading, spacing: 1) {
                    HStack(alignment: .firstTextBaseline) {
                        Text(row.title).font(.subheadline).foregroundStyle(.secondary)
                        Spacer(minLength: 8)
                        Text(row.value).font(.body).textSelection(.enabled)
                    }
                    Text(row.origin).font(.caption).foregroundStyle(.secondary)
                        .help(row.basis)
                }
                .accessibilityElement(children: .combine)
            }
        }
    }
}

/// Every live reading, grouped by kind; the one that counts is marked with WHY it counts.
struct InspectorTextSection: View {
    let text: InspectorText
    /// "Make This Count" on a reading that does not count; nil shows no verb (a preview, a reader).
    var onChoose: ((InspectorText.Reading) -> Void)?
    /// "Edit…" on the reading that counts (#5201); nil shows no verb.
    var onEdit: ((InspectorText.Reading) -> Void)?
    /// The run whose trace "View Run" shows.
    @State private var traceRun: TraceRunSelection?

    private struct TraceRunSelection: Identifiable {
        let threadId: String
        var id: String { threadId }
    }

    var body: some View {
        sections
            .sheet(item: $traceRun) { RunTraceSheet(threadId: $0.threadId) }
    }

    private var sections: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Readings").font(.headline)
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
                Text(reading.content).font(BundledFonts.shared.font(.body)).textSelection(.enabled)
            }
            HStack(spacing: 8) {
                Text(detail(reading, counts: counts)).font(.caption).foregroundStyle(.secondary)
                if reading.producerRunId != nil {
                    Button("View Run") {
                        guard let threadId = RunTraceLink.threadId(reading.producerRunId) else { return }
                        traceRun = TraceRunSelection(threadId: threadId)
                    }
                    .buttonStyle(.borderless)
                    .font(.caption)
                    .help("View the trace of the run that made this reading")
                }
                if !counts, let onChoose {
                    Button("Make This Count") { onChoose(reading) }
                        .buttonStyle(.borderless)
                        .font(.caption)
                        .help("Choose this reading as the one that counts for \(reading.kind)")
                }
                if counts, reading.kind == "transcription", let onEdit {
                    Button("Edit\u{2026}") { onEdit(reading) }
                        .buttonStyle(.borderless)
                        .font(.caption)
                        .help("Correct this reading; saved as your correction of it, as typing in the Reader is")
                }
            }
        }
    }

    /// Who made it, who wrote it down, the guideline, and -- for the one that counts -- why.
    private func detail(_ reading: InspectorText.Reading, counts: Bool) -> String {
        var parts = [reading.whoRead ?? reading.maker.capitalized]
        if let step = reading.producerStep { parts.append(step) }
        if let author = reading.author { parts.append(author) }
        if let created = reading.createdAt {
            parts.append(created.formatted(.relative(presentation: .named, unitsStyle: .abbreviated)))
        }
        if let guideline = reading.guideline { parts.append(guideline) }
        if let level = reading.level { parts.append("level \(level)") }
        if let confidence = reading.machineConfidence { parts.append("confidence \(Int((confidence * 100).rounded()))%") }
        if reading.correctsId != nil { parts.append("a correction") }
        if reading.readFromRenditionId != nil { parts.append("read from another image") }
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
