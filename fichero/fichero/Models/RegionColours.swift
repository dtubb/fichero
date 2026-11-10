import Foundation

/// Which colour a segment is drawn in (`segment-editor.md` "Box colour and the segment hierarchy", ruled
/// 2026-10-04, #5426, #5463): its REGION's hue, shaded along the working pass's reading order. The hue is the
/// REGION's own (owner 2026-11-08, #6419/#6422, superseding the 2026-10-04 order rule): a fixed hash of its id, so
/// deleting or adding another region never recolours it, and the same page draws the same way every time.
///
/// The ONE colour rule (#5467 part b). Every surface that colours a box reads a `Tone` from here and turns it
/// into a colour with `SelectionStyle.regionColour`: the Preview image overlay, the PDF page, the Inspector's
/// region rows.
nonisolated enum RegionColours {
    /// How many hues the palette has (`SelectionStyle.regionPalette`, system colours only).
    static let paletteCount = 12

    /// The last line of a region is drawn at this strength; the first at full (`colour.reading-order-gradient`).
    static let lightestStrength = 0.4  // 0.7 read as one colour down 19 lines (owner, 2026-11-10); 0.45 before 2026-10-09

    /// What colours a segment: its region's place in the palette, and how strongly it is drawn (1 for the
    /// first line in reading order, down to `lightestStrength` for the last).
    struct Tone: Hashable {
        let hue: Int
        let strength: Double
    }

    /// The display option "Shade by Reading Order" (Display menu); on unless a person turned it off.
    static let shadeKey = "preview.shadeByReadingOrder"
    static var shadesByOrder: Bool { UserDefaults.standard.object(forKey: shadeKey) as? Bool ?? true }

    /// Each segment's tone (`colour.region-hue`, `colour.reading-order-gradient`, `colour.never-random`,
    /// `colour.regionless-lines-are-one-region`).
    ///
    /// - A segment's region is its nearest ancestor of kind `region` (itself, for a region). Segments with no
    ///   region ancestor belong to ONE implicit region: the page's own.
    /// - A region's hue is `hue(ofRegion:)`, a fixed hash of its id; the implicit page region has its own constant.
    /// - Inside a region, the graded segments (its top non-region level: lines, or a word with no line) are
    ///   shaded evenly from `lightestStrength` (the first) to full strength (the last) in reading order, light to dark (owner 2026-11-10). Their children (words, letters)
    ///   take their shade. A region box is drawn at full strength.
    /// - `readingOrder` is the working pass's order (segment ids) when the caller holds one; nil means the
    ///   page's as-written order, which is the boxes' own order (`boxIndex`) -- the engine makes the as-written
    ///   order from it (`ConvertPageRequest`). Segments the order does not name follow it in as-written order.
    static func tones(of segments: [Segment], readingOrder: [String]? = nil,
                      shadeByOrder: Bool = RegionColours.shadesByOrder) -> [String: Tone] {
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let asWritten = segments.sorted { ($0.boxIndex ?? 0, $0.id) < ($1.boxIndex ?? 0, $1.id) }
        var sequence = (readingOrder ?? []).compactMap { byId[$0] }
        let named = Set(sequence.map(\.id))
        sequence += asWritten.filter { !named.contains($0.id) }

        // Walk up to the region (nil: the page's implicit one) and the graded segment at the top of the chain
        // below it (nil for a region itself).
        func place(of segment: Segment) -> (region: String?, graded: String?) {
            var cursor = segment
            var graded: String?
            var hops = 0
            while hops < 32 {
                if cursor.kind == "region" { return (cursor.id, graded) }
                graded = cursor.id
                guard let parentId = cursor.parentSegmentId, let parent = byId[parentId] else { break }
                cursor = parent
                hops += 1
            }
            return (nil, graded)
        }

        let implicitRegion = "\u{0}page"
        var hues: [String: Int] = [:]
        var gradedByRegion: [String: [String]] = [:]
        var places: [String: (region: String, graded: String?)] = [:]
        for segment in sequence {
            let found = place(of: segment)
            let region = found.region ?? implicitRegion
            places[segment.id] = (region, found.graded)
            if hues[region] == nil { hues[region] = region == implicitRegion ? 0 : hue(ofRegion: region) }
            if let graded = found.graded, !(gradedByRegion[region] ?? []).contains(graded) {
                gradedByRegion[region, default: []].append(graded)
            }
        }

        var gradedStrength: [String: Double] = [:]
        for (_, graded) in gradedByRegion {
            for (position, id) in graded.enumerated() {
                gradedStrength[id] = graded.count < 2
                    ? 1 : lightestStrength + (1 - lightestStrength) * Double(position) / Double(graded.count - 1)
            }
        }

        var tones: [String: Tone] = [:]
        for (id, found) in places {
            let strength = shadeByOrder ? (found.graded.flatMap { gradedStrength[$0] } ?? 1) : 1
            tones[id] = Tone(hue: hues[found.region] ?? 0, strength: strength)
        }
        return tones
    }

    /// A region's palette slot: FNV-1a over its kind and id (Swift's `Hasher` is seeded per launch, which would
    /// recolour every region on every start). Two regions can share a slot; none moves when another is deleted.
    // ponytail: no collision handling, any rule that avoids one depends on the other regions again; widen the palette.
    static func hue(ofRegion id: String) -> Int {
        var hash: UInt64 = 0xcbf29ce484222325
        for byte in "region:\(id)".utf8 {
            hash = (hash ^ UInt64(byte)) &* 0x100000001b3
        }
        return Int(hash % UInt64(paletteCount))
    }

    /// Each LINE's reading number, 1 up the page, in the order `tones` reads (the chosen order, else the boxes' own):
    /// the "Show Order Numbers" display switch. Regions and words carry none.
    static func orderNumbers(of segments: [Segment], readingOrder: [String]? = nil) -> [String: Int] {
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        let asWritten = segments.sorted { ($0.boxIndex ?? 0, $0.id) < ($1.boxIndex ?? 0, $1.id) }
        var sequence = (readingOrder ?? []).compactMap { byId[$0] }
        let named = Set(sequence.map(\.id))
        sequence += asWritten.filter { !named.contains($0.id) }
        var numbers: [String: Int] = [:]
        for segment in sequence where SegmentHierarchy.Level(kind: segment.kind) == .line {
            numbers[segment.id] = numbers.count + 1
        }
        return numbers
    }

    /// The legend's hues (`source.editor.hierarchy.legend`): each region's hue once, lowest first (two regions
    /// can share a slot). At most the palette's length.
    static func legend(of tones: [Tone]) -> [Int] {
        Array(Set(tones.map(\.hue))).sorted()
    }

    /// The tone a box from ANOTHER list of the same page is drawn in on the Preview: the seam's box with the
    /// same identity (`BoxKey`), or nil when the seam draws no such box (artifact geometry, drawn plain). How the
    /// Inspector's rows, which list the artifact's boxes, colour each row as the Preview draws it.
    @MainActor
    static func tone(of box: OCRGeometryBox, drawnIn seam: OCRGeometry?) -> Tone? {
        guard let seam else { return nil }
        let key = BoxKey(box)
        return seam.boxes.first { BoxKey($0) == key }?.tone
    }
}
