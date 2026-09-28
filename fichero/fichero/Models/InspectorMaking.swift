import Foundation

/// The Inspector's Making section at PAGE level (#5149; `build-notes-inspector.md` 5.9): how each of
/// the page's passes came to be -- "Imported from 0065.xml · PAGE XML · 22 lines, 4 regions" -- and
/// whether its original can be shown. Pure, over what the segment store already holds.
enum InspectorMaking {
    struct Entry: Equatable, Identifiable {
        let passId: String
        /// "Imported from <file>", or the pass's own name for a pass not made from a file.
        let title: String
        /// "PAGE XML · 12 lines, 4 regions".
        let detail: String
        let hasOriginal: Bool
        var id: String { passId }
    }

    /// One entry per real (non-provisional) pass of the page, imported ones first, then by name.
    static func entries(passes: [SegmentPassValue], segments: [Segment]) -> [Entry] {
        let byPass = Dictionary(grouping: segments, by: \.passId)
        return passes.filter { !$0.provisional }
            .sorted { ($0.importFile == nil ? 1 : 0, $0.name) < ($1.importFile == nil ? 1 : 0, $1.name) }
            .map { pass in
                let title = pass.importFile.map { "Imported from \($0)" } ?? pass.name
                var parts: [String] = []
                if let format = pass.importFormat { parts.append(formatName(format)) }
                parts.append(counts(byPass[pass.id] ?? []))
                return Entry(
                    passId: pass.id, title: title, detail: parts.joined(separator: " · "),
                    hasOriginal: pass.hasOriginal
                )
            }
    }

    /// The format as people write it.
    static func formatName(_ format: String) -> String {
        switch format {
        case "pagexml": "PAGE XML"
        case "alto": "ALTO"
        case "tei": "TEI"
        case "hocr": "hOCR"
        case "yolo": "YOLO"
        default: format
        }
    }

    /// "12 lines, 4 regions": most first, then by name; plural by count.
    static func counts(_ segments: [Segment]) -> String {
        var byKind: [String: Int] = [:]
        for segment in segments { byKind[segment.kind, default: 0] += 1 }
        guard !byKind.isEmpty else { return "no segments" }
        return byKind.sorted { $0.value != $1.value ? $0.value > $1.value : $0.key < $1.key }
            .map { "\($0.value) \($0.value == 1 ? $0.key : $0.key + "s")" }
            .joined(separator: ", ")
    }
}
