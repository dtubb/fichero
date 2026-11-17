@testable import Fichero
import Testing

/// `source.editor.two-switches` (ruled 2026-09-27 Q2: the switches are layers). Owner 2026-11-17: showing and hiding
/// segments did not work, they were always on or not at all: on an image only the words could be hidden (regions and
/// lines were always drawn, and Show Regions hid only old region marks); on a PDF, Show Word Bounding Boxes off hid every
/// box. Each level now has its own switch, the same on both.
struct PreviewLayerSwitchesTests {
    @Test("source.editor.two-switches: Show Regions, Show Lines and Show Word Bounding Boxes each hide their own level")
    func eachLevelItsOwnSwitch() {
        let levels: [SegmentHierarchy.Level] = [.region, .line, .word, .letter]
        let shown = { (regions: Bool, lines: Bool, words: Bool) in
            levels.filter { SegmentHierarchy.shows($0, regions: regions, lines: lines, words: words) }
        }
        #expect(shown(true, true, true) == levels)
        #expect(shown(false, true, true) == [.line, .word, .letter])
        #expect(shown(true, false, true) == [.region, .word, .letter])
        #expect(shown(true, true, false) == [.region, .line], "words off keeps regions and lines")
        #expect(shown(false, false, false).isEmpty, "everything can be hidden")
    }
}
