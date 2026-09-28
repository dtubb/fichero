@testable import Fichero
import SwiftUI
import XCTest

#if os(macOS)
/// Drawing a region, the rubber band was drawn below and right of the pointer while the region it made
/// landed where it should (#5214, Daniel's hebrew-rtl screenshot). The layer placed every child by `.offset`
/// from its origin but framed itself with the default CENTRE alignment, so with only the band drawn its
/// content was centred in the pane. What breaks without this: the band drifts from the pointer again, by
/// half the pane minus the band, and a person drawing cannot see what they are drawing.
@MainActor
final class RegionBandFollowsThePointerTests: XCTestCase {
    private let size = CGSize(width: 400, height: 300)

    func testAtEachDragPointTheBandIsWhereTheRegionWillBe() async throws {
        let feed = PreviewPointerFeed()
        let layer = RegionInteractionLayer(
            boxes: [], allBoxes: [], visible: CGRect(x: 0, y: 0, width: 1, height: 1), artifactId: nil,
            documentId: "page", marquees: nil, imagePixelSize: nil, isAddingRegion: true,
            drawsSelection: false,  // as the Mac preview mounts it: the band is then the layer's only drawing
            pointer: feed,
            onMoveCommit: { _, _ in }, onPromote: { _, _ in }, onOpenRegion: { _ in }, selection: RegionSelection()
        )
        let window = NSWindow(contentRect: CGRect(origin: CGPoint(x: 100, y: 100), size: size),
                              styleMask: [.borderless], backing: .buffered, defer: false)
        let host = NSHostingView(rootView: layer.frame(width: size.width, height: size.height))
        window.contentView = host
        defer { window.contentView = nil }

        feed.publish(PreviewPointerEvent(phase: .pressed, point: CGPoint(x: 0.1, y: 0.2), shift: false, clickCount: 1))
        for end in [CGPoint(x: 0.3, y: 0.35), CGPoint(x: 0.6, y: 0.5), CGPoint(x: 0.25, y: 0.8)] {
            feed.publish(PreviewPointerEvent(phase: .dragged, point: end, shift: false, clickCount: 1))
            // The overlay's own mapping of the rectangle dragged so far -- what the region will be.
            let want = try XCTUnwrap(BoundingBoxGeometry.viewRect(
                normalized: [Double(min(0.1, end.x)), Double(min(0.2, end.y)),
                             Double(abs(end.x - 0.1)), Double(abs(end.y - 0.2))],
                in: size, visible: CGRect(x: 0, y: 0, width: 1, height: 1)
            ))
            // SwiftUI applies the pointer on a later turn: wait for the band to reach this drag's size.
            var drawn = CGRect.null
            for _ in 0..<100 {
                host.layoutSubtreeIfNeeded()
                if let band = Self.element(RegionInteractionLayer.liveBandIdentifier, under: host) {
                    drawn = Self.viewRect(ofScreenFrame: band.accessibilityFrame(), in: host)
                    if abs(drawn.width - want.width) < 1, abs(drawn.height - want.height) < 1 { break }
                }
                try await Task.sleep(nanoseconds: 10_000_000)
            }
            XCTAssertFalse(drawn.isNull, "the band is drawn")
            XCTAssertEqual(drawn.minX, want.minX, accuracy: 1, "the band starts where the press was, at \(end)")
            XCTAssertEqual(drawn.minY, want.minY, accuracy: 1, "not below it")
            XCTAssertEqual(drawn.width, want.width, accuracy: 1)
            XCTAssertEqual(drawn.height, want.height, accuracy: 1)
        }
    }

    /// The first accessibility element with this identifier, depth first.
    private static func element(_ identifier: String, under root: Any) -> NSAccessibilityElementProtocol? {
        guard let node = root as? NSAccessibilityElementProtocol & NSObject else { return nil }
        if (node as? NSAccessibilityProtocol)?.accessibilityIdentifier() == identifier { return node }
        for child in (node as? NSAccessibilityProtocol)?.accessibilityChildren() ?? [] {
            if let found = element(identifier, under: child) { return found }
        }
        return nil
    }

    /// A screen frame (bottom-left origin) back in the host's top-left view coordinates.
    private static func viewRect(ofScreenFrame frame: CGRect, in host: NSView) -> CGRect {
        let inWindow = host.window?.convertFromScreen(frame) ?? frame
        let inView = host.convert(inWindow, from: nil)
        return host.isFlipped ? inView : CGRect(x: inView.minX, y: host.bounds.height - inView.maxY,
                                                width: inView.width, height: inView.height)
    }
}
#endif
