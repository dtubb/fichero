import Foundation

/// Mark Unclear, Lost or Supplied on a stretch selected in the Reader (`source.editor.mark-a-stretch-unclear-from-the-reader`, #6451,
/// #6454): the selection becomes one `editorial.record` request per line it touches, each span in CODE POINTS (what the engine's
/// strings count) measured on the reading SHOWN for that line. Pure: no view, no network.
enum ReaderMark {
    enum Kind: String, CaseIterable, Identifiable {
        case unclear, lost, supplied
        var id: String { rawValue }

        var title: String {
            switch self {
            case .unclear: "Unclear"
            case .lost: "Lost"
            case .supplied: "Supplied"
            }
        }
    }

    /// One line as the Reader shows it: its segment, the reading shown (the counting one) and that reading's text.
    struct Line: Equatable {
        let segmentId: String
        let representationId: String
        let text: String
    }

    /// `selection` is a UTF-16 range over the shown lines joined with one newline between them (what a text view reports). A
    /// line the selection only touches at its edge, or a newline alone, gets no request. An empty selection marks nothing.
    static func requests(_ kind: Kind, lines: [Line], selection: NSRange) -> [EditorialRecordRequest] {
        guard selection.length > 0 else { return [] }
        var out: [EditorialRecordRequest] = []
        var offset = 0
        for line in lines {
            let length = line.text.utf16.count
            let start = max(selection.location, offset), end = min(NSMaxRange(selection), offset + length)
            if start < end, let span = codePoints(of: line.text, utf16From: start - offset, to: end - offset) {
                out.append(EditorialRecordRequest(
                    segmentId: line.segmentId, kind: kind.rawValue, representationId: line.representationId,
                    charStart: span.start, charEnd: span.end, place: nil
                ))
            }
            offset += length + 1
        }
        return out
    }

    private static func codePoints(of text: String, utf16From: Int, to utf16To: Int) -> (start: Int, end: Int)? {
        let units = text.utf16
        guard let low = units.index(units.startIndex, offsetBy: utf16From, limitedBy: units.endIndex),
              let high = units.index(units.startIndex, offsetBy: utf16To, limitedBy: units.endIndex),
              let start = low.samePosition(in: text.unicodeScalars),
              let end = high.samePosition(in: text.unicodeScalars) else { return nil }
        let scalars = text.unicodeScalars
        return (scalars.distance(from: scalars.startIndex, to: start), scalars.distance(from: scalars.startIndex, to: end))
    }
}
