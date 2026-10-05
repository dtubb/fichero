import Foundation

/// The Reader marks each region's block of lines with a rule in the region's hue down its leading edge
/// (`source.editor.hierarchy.reader-shows-regions`, hierarchy A, #5426). The page's half draws the rule
/// (`window.fichero.showRegions` in `document_view.html`); this is the app's: which lines make each region's
/// block, and its hue -- from the ONE colour path (`RegionColours.tones`), sent as the palette NAME
/// (`SelectionStyle.regionPaletteNames`), never RGB, so the page resolves the system colour for the appearance.
nonisolated enum ReaderRegionRules {
    struct Block: Equatable, Encodable {
        /// The region's lines, in the page's as-written order.
        let segmentIds: [String]
        /// The region's palette name.
        let hue: String
    }

    /// Each region's block on a page: its lines (the `line` kind) under their nearest region ancestor, in
    /// as-written order, the hue the Preview draws the region in. Lines with no region are the page's one
    /// implicit region, ruled in its hue too (`colour.regionless-lines-are-one-region`).
    static func blocks(_ segments: [Segment]) -> [Block] {
        let tones = RegionColours.tones(of: segments)
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        func region(of segment: Segment) -> String {
            var cursor = segment.parentSegmentId.flatMap { byId[$0] }
            var hops = 0
            while let parent = cursor, hops < 32 {
                if parent.kind == "region" { return parent.id }
                cursor = parent.parentSegmentId.flatMap { byId[$0] }
                hops += 1
            }
            return ""
        }
        let lines = segments
            .filter { SegmentHierarchy.Level(kind: $0.kind) == .line }
            .sorted { ($0.boxIndex ?? 0, $0.id) < ($1.boxIndex ?? 0, $1.id) }
        var order: [String] = []
        var members: [String: [String]] = [:]
        var hues: [String: String] = [:]
        for line in lines {
            let key = region(of: line)
            if members[key] == nil { order.append(key) }
            members[key, default: []].append(line.id)
            if hues[key] == nil, let tone = tones[line.id] { hues[key] = SelectionStyle.regionPaletteName(tone) }
        }
        return order.compactMap { key in
            guard let ids = members[key], let hue = hues[key] else { return nil }
            return Block(segmentIds: ids, hue: hue)
        }
    }

    /// The call that rules `blocks` on the page; an empty list clears. Optional-chained, so a page without it
    /// ignores it rather than throwing.
    static func showRegionsScript(_ blocks: [Block]) -> String {
        let data = (try? JSONEncoder().encode(blocks)) ?? Data()
        let json = String(bytes: data, encoding: .utf8) ?? "[]"
        return "window.fichero?.showRegions?.(\(json));"
    }
}
