@testable import Fichero
import Foundation
import Testing

/// The per-turn body tally and the live-resize line name what a slow click or resize did.
@Suite("Render diagnostics say what a slow turn rebuilt")
struct RenderTimingDiagnosticsTests {

    @Test("a busy turn lists its views, most evaluated first")
    func busyTurnIsRankedLargestFirst() {
        let line = BodyCount.summary(["LibraryView": 2, "SidebarItemRow": 120, "PaneHead": 2], threshold: 20)
        #expect(line == "124 · SidebarItemRow 120 · LibraryView 2 · PaneHead 2")
    }

    @Test("a quiet turn logs nothing")
    func quietTurnIsSilent() {
        #expect(BodyCount.summary(["SidebarItemRow": 3], threshold: 20) == nil)
    }

    @Test("a live resize reports its frames, average and slowest")
    func resizeReportsFrames() {
        let milli: UInt64 = 1_000_000
        // start, two frames, end: gaps of 10, 30 and 20 ms.
        let stamps = [100 * milli, 110 * milli, 140 * milli, 160 * milli]
        #expect(ResizeProfile.summary(stamps) == "took 60.0ms: 2 frames, average 20.0ms, slowest 30.0ms")
    }

    @Test("a resize with no frame between start and end reports nothing")
    func resizeWithoutFramesIsSilent() {
        #expect(ResizeProfile.summary([1, 2]) == nil)
    }
}
