@testable import Fichero
import Testing

@Suite("ActivityStreamService reconnect state")
struct ActivityStreamServiceTests {

    @Test("the unavailable pill appears on the second consecutive failure")
    func unavailableThreshold() {
        #expect(!ActivityStreamService.shouldSurfaceUnavailable(failureCount: 0))
        #expect(!ActivityStreamService.shouldSurfaceUnavailable(failureCount: 1))
        #expect(ActivityStreamService.shouldSurfaceUnavailable(failureCount: 2))
        #expect(ActivityStreamService.shouldSurfaceUnavailable(failureCount: 3))
    }

    @Test("initial connection failures stay owned by the app-level connection gate")
    func initialConnectionDoesNotSurfacePausedPill() {
        #expect(!ActivityStreamService.shouldSurfaceAfterDrop(failureCount: 2, hasConnectedBefore: false))
        #expect(!ActivityStreamService.shouldSurfaceAfterDrop(failureCount: 10, hasConnectedBefore: false))
    }

    @Test("post-connect drops use the same two-strike threshold")
    func postConnectDropUsesThreshold() {
        #expect(!ActivityStreamService.shouldSurfaceAfterDrop(failureCount: 1, hasConnectedBefore: true))
        #expect(ActivityStreamService.shouldSurfaceAfterDrop(failureCount: 2, hasConnectedBefore: true))
    }
}
