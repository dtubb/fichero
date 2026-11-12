import FicheroAPIClient
import Foundation

/// The page's other readings for the Segments list (`source.editor.segment-row-is-the-same-in-every-lens`, Step 1.27,
/// #6492), from the engine's one compare answer for the page (`GET /api/documents/{page}/compare-readers`): the readers to
/// tick in the pane's view menu, each ticked reader's words under a row, and the words a row shows -- the counting
/// reading's, not the segment's raw text. Pure: the engine does the matching, this only picks what a row shows.
struct SegmentOtherReadings: Equatable {
    struct Reader: Equatable, Identifiable {
        let id: String
        let label: String
    }

    /// One reader's words under a row, labelled with the reader.
    struct Line: Equatable {
        let reader: String
        let text: String
    }

    let readers: [Reader]
    /// Each segment's text per reader id, for the lines the engine matched to a segment.
    private let texts: [String: [String: String]]
    /// Each segment's counting reader, when one counts.
    private let counting: [String: String]

    /// One compare line, as far as a row needs it.
    struct Matched {
        let segmentId: String?
        let counting: String?
        let readings: [(reader: String, text: String)]
    }

    init(readers: [Reader], lines: [Matched]) {
        self.readers = readers
        var texts: [String: [String: String]] = [:]
        var counting: [String: String] = [:]
        for line in lines {
            guard let segment = line.segmentId else { continue }
            for reading in line.readings where texts[segment]?[reading.reader] == nil {
                texts[segment, default: [:]][reading.reader] = reading.text
            }
            if let reader = line.counting { counting[segment] = reader }
        }
        self.texts = texts
        self.counting = counting
    }

    init(answer: Components.Schemas.CompareReadersResponse) {
        self.init(
            readers: answer.readers.map { Reader(id: $0.id, label: $0.label) },
            lines: answer.lines.map { line in
                Matched(segmentId: line.segmentId, counting: line.countingReaderId,
                        readings: line.readings.map { ($0.readerId, $0.text) })
            }
        )
    }

    /// The ticked readers' words under a row, in the readers' order; a reader that did not read it gives nothing.
    /// Ticks are kept by the reader's label, so a choice made on one page holds on the next.
    func under(_ segmentId: String, ticked: Set<String>) -> [Line] {
        guard !ticked.isEmpty, let byReader = texts[segmentId] else { return [] }
        return readers.compactMap { reader in
            guard ticked.contains(reader.label), let text = byReader[reader.id]?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !text.isEmpty else { return nil }
            return Line(reader: reader.label, text: text)
        }
    }

    /// The words a row shows: the counting reading's; nil where none counts (the row keeps the segment's own text).
    func shown(_ segmentId: String) -> String? {
        guard let reader = counting[segmentId], let text = texts[segmentId]?[reader], !text.isEmpty else { return nil }
        return text
    }

    /// The ticked labels as kept per window: one per line.
    static func decode(_ raw: String) -> Set<String> { Set(raw.split(separator: "\n").map(String.init)) }
    static func encode(_ ticked: Set<String>) -> String { ticked.sorted().joined(separator: "\n") }
}
