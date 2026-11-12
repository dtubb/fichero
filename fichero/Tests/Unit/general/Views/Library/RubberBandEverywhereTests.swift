@testable import Fichero
import SwiftUI
import Testing

/// One rubber band everywhere (#4601, `library.selection.one-rubber-band`; owner 2026-11-11: Finder's band, neutral grey,
/// never the accent, which may be yellow). What breaks without this: one surface keeps its own accent box and the
/// boards, the grid and the Preview each sweep in a different colour.
struct RubberBandEverywhereTests {
    @Test("the band is grey and semantic, never the accent")
    func theBandIsNeutral() {
        #expect(RubberBand.fill == Color.secondary.opacity(0.12))
        #expect(RubberBand.border == Color.secondary.opacity(0.5))
        #expect(RubberBand.lineWidth == 1)
    }
}
