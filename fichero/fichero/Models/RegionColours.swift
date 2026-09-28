import Foundation

/// Which colour a segment is drawn in (`source.editor.regions-in-colours`, #5200): its region's, from a
/// fixed palette of system colours keyed by a STABLE hash of the region's id, so a region keeps its colour
/// across launches, panes and machines. Within a region, lines alternate two tints in the region's order,
/// so overlapping neighbours stay apart with thin outlines (#5207).
nonisolated enum RegionColours {
    /// How many colours the palette has (`SelectionStyle.regionPalette`, system colours only).
    static let paletteCount = 12

    /// A region id's place in the palette: FNV-1a over its UTF-8 bytes. Never `hashValue`, which Swift
    /// seeds afresh every launch.
    static func paletteIndex(for regionId: String) -> Int {
        var hash: UInt64 = 0xcbf29ce484222325
        for byte in regionId.utf8 {
            hash ^= UInt64(byte)
            hash = hash &* 0x100000001b3
        }
        return Int(hash % UInt64(paletteCount))
    }

    /// What colours a segment: its region, and whether it takes the lighter tint.
    struct Tone: Equatable {
        let regionId: String
        let alternate: Bool
    }

    /// Each segment's tone. A segment's region is its nearest ancestor of kind `region`, else its topmost
    /// ancestor, else itself. Lines alternate within their region in the order given (the page's as-written
    /// order, `boxIndex`); other kinds take the region's colour plain.
    /// ponytail: as-written order; a named reading order would change which line is which tint.
    static func tones(of segments: [Segment]) -> [String: Tone] {
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        func region(of segment: Segment) -> String {
            var cursor = segment
            var hops = 0
            while cursor.kind != "region", let parentId = cursor.parentSegmentId, let parent = byId[parentId], hops < 16 {
                cursor = parent
                hops += 1
            }
            return cursor.id
        }
        var tones: [String: Tone] = [:]
        var linesSeen: [String: Int] = [:]
        for segment in segments.sorted(by: { ($0.boxIndex ?? 0, $0.id) < ($1.boxIndex ?? 0, $1.id) }) {
            let regionId = region(of: segment)
            var alternate = false
            if segment.kind == "line" {
                let seen = linesSeen[regionId, default: 0]
                alternate = seen % 2 == 1
                linesSeen[regionId] = seen + 1
            }
            tones[segment.id] = Tone(regionId: regionId, alternate: alternate)
        }
        return tones
    }
}
