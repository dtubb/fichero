@testable import Fichero
import Foundation
import Testing

/// A click or drag on the 2D board logs one line naming how often the board was resolved and
/// reconciled while it lasted (`library.canvas.click-and-drag-are-timed`, #5253).
@Suite("Canvas board click and drag timing", .serialized)
@MainActor
struct CanvasBoardProfileTests {

    /// One main-queue turn: a block queued before this one has run when it returns.
    private func nextTurn() async {
        await withCheckedContinuation { continuation in
            DispatchQueue.main.async { continuation.resume() }
        }
    }

    @Test("a click's line splits the hold from the release and counts the board's work")
    func clickSummary() {
        var press = CanvasBoardProfile.Press(started: 1_000_000_000)
        press.released = 1_090_000_000
        press.resolves = 4
        press.resolveNanos = 60_000_000
        press.reconciles = 4
        press.reconcileNanos = 20_000_000
        #expect(
            CanvasBoardProfile.summary(press, ended: 1_180_000_000)
                == "canvas click took 180.0ms: held 90.0ms, release → drawn 90.0ms; "
                + "resolved 4 times, 60.0ms; reconciled 4 times, 20.0ms"
        )
    }

    @Test("a click logs once the frame after the release has passed, with the work inside it")
    func clickCountsWorkInside() async throws {
        var logged: String?
        CanvasBoardProfile.mouse(.pressed)
        _ = CanvasBoardProfile.timing(.resolve) { 1 }
        CanvasBoardProfile.mouse(.released) { logged = $0 }
        // Work done in the release's own turn (the tap's state change) still counts.
        _ = CanvasBoardProfile.timing(.resolve) { 2 }
        CanvasBoardProfile.timing(.reconcile) {}
        await nextTurn()
        let line = try #require(logged)
        #expect(line.hasPrefix("canvas click took"))
        #expect(line.contains("resolved 2 times"))
        #expect(line.contains("reconciled 1 times"))
        #expect(CanvasBoardProfile.press == nil)
    }

    @Test("a drag counts its moves, and work outside a press is not counted")
    func dragCountsMoves() async throws {
        _ = CanvasBoardProfile.timing(.resolve) { 0 }
        var logged: String?
        CanvasBoardProfile.mouse(.pressed)
        CanvasBoardProfile.mouse(.dragged)
        CanvasBoardProfile.mouse(.dragged)
        await nextTurn()
        CanvasBoardProfile.mouse(.released) { logged = $0 }
        await nextTurn()
        let line = try #require(logged)
        #expect(line.hasPrefix("canvas drag took"))
        #expect(line.contains(": 2 moves,"))
        #expect(line.contains("resolved 0 times"))
    }

    @Test("a release with no press logs nothing")
    func releaseWithoutPress() async {
        var logged: String?
        CanvasBoardProfile.mouse(.released) { logged = $0 }
        await nextTurn()
        #expect(logged == nil)
    }
}
