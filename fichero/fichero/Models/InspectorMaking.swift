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
        /// The page's working pass -- the one its text and edits come from -- and why (#5156).
        var working = false
        var workingNote: String?
        /// A georeferencing pass (control points and a mask): listed apart from the text passes, and
        /// never offered as the page's working TEXT pass (#5122).
        var georeferencing = false
        var id: String { passId }
    }

    /// One entry per real (non-provisional) pass of the page: text passes first, then georeferencing
    /// ones; within each, imported ones first, then by name.
    static func entries(passes: [SegmentPassValue], segments: [Segment]) -> [Entry] {
        let byPass = Dictionary(grouping: segments, by: \.passId)
        return passes.filter { !$0.provisional }
            .sorted {
                ($0.isGeoreferencing ? 1 : 0, $0.importFile == nil ? 1 : 0, $0.name)
                    < ($1.isGeoreferencing ? 1 : 0, $1.importFile == nil ? 1 : 0, $1.name)
            }
            .map { pass in
                let title = pass.importFile.map { "Imported from \($0)" } ?? pass.name
                var parts: [String] = []
                if let format = pass.importFormat { parts.append(formatName(format)) }
                parts.append(counts(byPass[pass.id] ?? []))
                return Entry(
                    passId: pass.id, title: title, detail: parts.joined(separator: " · "),
                    hasOriginal: pass.hasOriginal, working: pass.working,
                    workingNote: pass.working ? workingNote(pass.workingBasis) : nil,
                    georeferencing: pass.isGeoreferencing
                )
            }
    }

    /// Why the working pass is the working one, in words.
    static func workingNote(_ basis: String?) -> String {
        switch basis {
        case "chosen": "Working · chosen by a person"
        case nil: "Working"
        default: "Working · by the project's rule"
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
        case "iiif-georef": "IIIF Georeference"
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
