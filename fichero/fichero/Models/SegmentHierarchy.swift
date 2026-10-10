import Foundation

/// How a child is drawn as its parent's child (`segment-editor.md` "Box colour and the segment hierarchy",
/// ruled 2026-10-05: **A -- nested, inheriting, lighter**, #5426). Every level draws at once: the region as a
/// faint wash of its hue with a thin outline, its lines as thin outlines in their reading-order shade, words and
/// letters as hairlines in their line's shade -- each inside its parent and LIGHTER than it. The colour itself
/// is `RegionColours.tones` (the one colour path); this decides only how strongly, how thick, and what a
/// selection does to the rest of the page. Pure, so a test reaches every rule.
nonisolated enum SegmentHierarchy {
    /// A segment's level on the page, coarsest first.
    enum Level: Int, Comparable {
        case region, line, word, letter

        static func < (lhs: Level, rhs: Level) -> Bool { lhs.rawValue < rhs.rawValue }

        /// A kind's level. Anything that holds lines (a region, a block, a table, the page) draws as a region;
        /// anything finer than a word (a glyph, a character) as a letter.
        init(kind: String) {
            switch kind.lowercased() {
            case "line", "textline": self = .line
            case "word": self = .word
            case "glyph", "character", "char", "letter": self = .letter
            default: self = .region
            }
        }
    }

    /// How strongly a level's outline is drawn, times its tone's strength: each finer level lighter than the
    /// one it sits in. A line's shade is at most 1 (`RegionColours`), so a line (<= 0.8) is always lighter
    /// than its region (1), and a word (its line's shade x 0.7) lighter than its line.
    static func strokeStrength(_ level: Level) -> Double {
        switch level {
        case .region: 1
        case .line: 0.8
        case .word: 0.7
        case .letter: 0.4
        }
    }

    /// The outline's width, times the system line width: a region and a line thin, a word and a letter hairlines.
    static func widthFactor(_ level: Level) -> Double {
        level <= .line ? 1 : 0.5
    }

    /// The region's faint wash of its hue (no other level fills at rest; hover and selection do).
    static let regionWash = 0.1

    /// What the selection does to one box (`children-drawn-as-children`): selecting a parent LIGHTS its
    /// children and DIMS what is outside it; selecting a child shows its PARENT's outline at full strength.
    enum Emphasis: Equatable {
        /// Nothing selected, or the selected box itself (drawn again by `SelectionStyle` on top).
        case rest
        /// Inside a selected box: drawn at its tone's full shade, the level's lightening lifted.
        case lit
        /// An ancestor of a selected box: its outline at full strength.
        case parent
        /// Outside every selected box and not its ancestor.
        case dimmed
    }

    /// How far outside a selection fades.
    static let dimmedFactor = 0.3

    /// Each box's emphasis, by segment id, for `selected` segment ids and the page's `parents` (child id ->
    /// parent id). Empty selection: every box at rest. A flat pass (no parents) lights nothing and shows no
    /// parent: the selected box alone stands out and the rest dims.
    static func emphasis(
        of ids: [String], parents: [String: String], selected: Set<String>
    ) -> [String: Emphasis] {
        guard !selected.isEmpty else { return [:] }
        var ancestors: Set<String> = []
        for id in selected {
            var cursor = parents[id]
            var hops = 0
            while let parent = cursor, hops < 32 {
                ancestors.insert(parent)
                cursor = parents[parent]
                hops += 1
            }
        }
        func isInside(_ id: String) -> Bool {
            var cursor = parents[id]
            var hops = 0
            while let parent = cursor, hops < 32 {
                if selected.contains(parent) { return true }
                cursor = parents[parent]
                hops += 1
            }
            return false
        }
        var out: [String: Emphasis] = [:]
        for id in ids {
            if selected.contains(id) {
                out[id] = .rest
            } else if isInside(id) {
                out[id] = .lit
            } else if ancestors.contains(id) {
                out[id] = .parent
            } else {
                out[id] = .dimmed
            }
        }
        return out
    }

    /// The opacity a box's outline is drawn at, before its confidence: its tone's shade (`toneStrength`) times
    /// its level's lightening, changed by the selection. The parent of a selection is drawn at full strength,
    /// ignoring its shade; a lit child at its tone's shade.
    static func strokeOpacity(level: Level, toneStrength: Double, emphasis: Emphasis = .rest) -> Double {
        switch emphasis {
        case .rest: toneStrength * strokeStrength(level)
        case .lit: toneStrength
        case .parent: 1
        case .dimmed: toneStrength * strokeStrength(level) * dimmedFactor
        }
    }

    /// The region's wash, changed by the selection the same way (a region is never lit: it is no child).
    static func washOpacity(level: Level, emphasis: Emphasis = .rest) -> Double {
        guard level == .region else { return 0 }
        return emphasis == .dimmed ? regionWash * dimmedFactor : regionWash
    }

    /// The finest level among `kinds`: the one that sets its reading inline, so a page with words does not set
    /// each line's reading over its own words (`inline-text-fits-its-box`).
    static func finestLevel(_ kinds: some Sequence<String>) -> Level {
        kinds.reduce(Level.region) { max($0, Level(kind: $1)) }
    }
}
