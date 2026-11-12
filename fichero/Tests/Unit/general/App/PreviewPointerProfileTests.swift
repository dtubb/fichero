@testable import Fichero
import Foundation
import Testing

/// A drag on the Preview image is summed into one line on release: its moves, their waits for the
/// next frame, and the overlay rebuilds in between (`preview.page-click-and-drag-are-timed`, #5253).
@Suite("Preview click and drag timing", .serialized)
@MainActor
struct PreviewPointerProfileTests {

    /// One main-queue turn: a block queued before this one has run when it returns.
    private func nextTurn() async {
        await withCheckedContinuation { continuation in
            DispatchQueue.main.async { continuation.resume() }
        }
    }

    @Test("the summary names the moves, their waits and the overlay's share")
    func summaryNamesMovesWaitsAndOverlay() {
        var drag = PreviewPointerProfile.Drag(started: 1_000_000_000)
        drag.waits = [10_000_000, 30_000_000, 20_000_000]
        drag.overlayBuilds = 3
        drag.overlayNanos = 45_000_000
        #expect(
            PreviewPointerProfile.summary(drag, ended: 1_500_000_000)
                == "took 500.0ms: 3 moves, average 20.0ms, slowest 30.0ms; overlay rebuilt 3 times, 45.0ms"
        )
    }

    @Test("a press and release with no move is a click, not a drag")
    func aClickLogsNoDrag() {
        PreviewPointerProfile.pointer(.pressed)
        #expect(PreviewPointerProfile.pointer(.released) == nil)
        #expect(PreviewPointerProfile.drag == nil)
    }

    @Test("a drag counts each move once its frame has passed, and the overlay builds inside it")
    func aDragCountsMovesAndOverlayBuilds() async throws {
        PreviewPointerProfile.pointer(.pressed)
        PreviewPointerProfile.pointer(.dragged)
        _ = PreviewPointerProfile.timingOverlay { 1 }
        PreviewPointerProfile.pointer(.dragged)
        _ = PreviewPointerProfile.timingOverlay { 2 }
        await nextTurn()
        let line = try #require(PreviewPointerProfile.pointer(.released))
        #expect(line.contains(": 2 moves,"))
        #expect(line.contains("overlay rebuilt 2 times"))
        #expect(PreviewPointerProfile.drag == nil)
    }

    @Test("an overlay built outside a drag is not counted against the next one")
    func overlayOutsideADragIsNotCounted() async throws {
        _ = PreviewPointerProfile.timingOverlay { 0 }
        PreviewPointerProfile.pointer(.pressed)
        PreviewPointerProfile.pointer(.dragged)
        await nextTurn()
        let line = try #require(PreviewPointerProfile.pointer(.released))
        #expect(line.contains("overlay rebuilt 0 times"))
    }
}
