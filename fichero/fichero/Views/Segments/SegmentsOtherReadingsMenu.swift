import SwiftUI

/// The Segments pane's "Other Readings" submenu (#6492, `source.editor.segments-list-shows-other-readings-under-rows`): the
/// page's readers, each with a checkmark, kept per window by label; and the ticked readers' words under each row.
struct SegmentsOtherReadingsMenu: View {
    /// The page's compare answer as the rows need it; nil until it arrives.
    let readings: SegmentOtherReadings?
    /// The ticked readers' labels, one per line (`SegmentOtherReadings.encode`).
    @Binding var raw: String

    var body: some View {
        Menu("Other Readings") {
            let readers = readings?.readers ?? []
            if readers.isEmpty {
                Text(readings == nil ? "Reading the page's readers…" : "No other readers on this page")
            }
            ForEach(readers) { reader in
                Toggle(reader.label, isOn: Binding(
                    get: { SegmentOtherReadings.decode(raw).contains(reader.label) },
                    set: { isOn in
                        var ticked = SegmentOtherReadings.decode(raw)
                        if isOn { ticked.insert(reader.label) } else { ticked.remove(reader.label) }
                        raw = SegmentOtherReadings.encode(ticked)
                    }
                ))
            }
        }
    }

    /// The ticked readers' words under each row, caption style, each labelled with its reader; nil with none ticked.
    static func lines(_ readings: SegmentOtherReadings?, raw: String) -> ((String) -> AnyView)? {
        let ticked = SegmentOtherReadings.decode(raw)
        guard !ticked.isEmpty, let readings else { return nil }
        return { id in
            let lines = readings.under(id, ticked: ticked)
            guard !lines.isEmpty else { return AnyView(EmptyView()) }
            return AnyView(OtherReadingLines(lines: lines))
        }
    }
}

/// One row's other readings: the reader's name, then its words.
struct OtherReadingLines: View {
    let lines: [SegmentOtherReadings.Line]

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            ForEach(lines, id: \.reader) { line in
                (Text(line.reader + "  ").foregroundStyle(.tertiary) + Text(line.text).foregroundStyle(.secondary))
                    .font(.caption)
                    .lineLimit(2)
                    .accessibilityLabel("\(line.reader): \(line.text)")
            }
        }
    }
}

#Preview("Other readings under a row") {
    VStack(alignment: .leading, spacing: 2) {
        Text("Line 3 · Item dixo que la capilla")
        OtherReadingLines(lines: [
            .init(reader: "Kraken", text: "Yten dixo q la capilla"),
            .init(reader: "Gemini", text: "Item dixo que la capilla")
        ])
    }
    .padding()
    .frame(width: 320, alignment: .leading)
}
