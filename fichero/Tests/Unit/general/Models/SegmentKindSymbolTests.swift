import Testing
@testable import Fichero

/// The kind icons: every kind maps to a symbol, and the four levels differ.
struct SegmentKindSymbolTests {
    @Test func eachLevelHasItsOwnSymbol() {
        let names = [SegmentHierarchy.Level.region, .line, .word, .letter].map(\.symbolName)
        #expect(Set(names).count == 4)
    }

    @Test func kindsMapThroughTheLadder() {
        #expect(SegmentHierarchy.Level(kind: "textline").symbolName == SegmentHierarchy.Level.line.symbolName)
        #expect(SegmentHierarchy.Level(kind: "block").symbolName == SegmentHierarchy.Level.region.symbolName)
    }
}
