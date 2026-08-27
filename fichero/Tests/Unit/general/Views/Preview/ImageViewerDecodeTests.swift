#if canImport(AppKit)
@testable import Fichero
import Testing

/// #3864 — image decode moved OFF the main thread. When a decode completes it must
/// apply only if it's still the latest request, so a fast page-flip drops the
/// superseded decode instead of flashing a stale page in. These lock that token.
@MainActor
struct ImageViewerDecodeTests {

    @Test("A newer image-load supersedes the prior token")
    func newLoadSupersedesPrior() {
        let coordinator = ImageWithCursorTracking.Coordinator()

        let first = coordinator.beginImageLoad()
        #expect(coordinator.isCurrentImageLoad(first))

        let second = coordinator.beginImageLoad()
        #expect(!coordinator.isCurrentImageLoad(first), "the first decode must be dropped once superseded")
        #expect(coordinator.isCurrentImageLoad(second))
    }

    @Test("Tokens are monotonic and unique so stale completions can't match")
    func tokensAreMonotonic() {
        let coordinator = ImageWithCursorTracking.Coordinator()
        let tokens = (0..<5).map { _ in coordinator.beginImageLoad() }
        #expect(Set(tokens).count == tokens.count)
        // Only the last one is current.
        for token in tokens.dropLast() {
            #expect(!coordinator.isCurrentImageLoad(token))
        }
        #expect(coordinator.isCurrentImageLoad(tokens.last!))
    }
}
#endif
