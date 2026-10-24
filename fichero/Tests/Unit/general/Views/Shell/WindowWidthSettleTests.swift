@testable import Fichero
import Foundation
import Testing

/// #6009: an Inspector drag must cost one layout write, not one per frame.
@MainActor
struct WindowWidthSettleTests {
    @Test("a burst of readings applies once, with the last")
    func burstAppliesOnceWithTheLast() async throws {
        let settle = WindowWidthSettle()
        var applied: [Double] = []
        for width in [1400.0, 1399.0, 1380.0, 1360.0] {
            settle.schedule(after: .milliseconds(40)) { applied.append(width) }
        }
        try await Task.sleep(for: .milliseconds(200))
        #expect(applied == [1360.0])
    }

    @Test("a reading is new only when it is a real width that moved by half a point")
    func newWidthRule() {
        #expect(!WindowWidthSettle.isNewWidth(0, since: 1400))
        #expect(!WindowWidthSettle.isNewWidth(1400.3, since: 1400))
        #expect(WindowWidthSettle.isNewWidth(1399, since: 1400))
        #expect(WindowWidthSettle.isNewWidth(1400, since: 0))
    }
}
