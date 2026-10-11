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

    /// Where the layer last laid the band out. A class so the layer's closure and the test share it.
    private final class BandProbe {
        var frame = CGRect.null
    }

    func testAtEachDragPointTheBandIsWhereTheRegionWillBe() async throws {
        let feed = PreviewPointerFeed()
        let probe = BandProbe()
        let layer = RegionInteractionLayer(
            boxes: [], allBoxes: [], visible: CGRect(x: 0, y: 0, width: 1, height: 1), artifactId: nil,
            documentId: "page", marquees: nil, imagePixelSize: nil, isAddingRegion: true,
            drawsSelection: false,  // as the Mac preview mounts it: the band is then the layer's only drawing
            pointer: feed, onBandFrame: { probe.frame = $0 },
            onMoveCommit: { _, _ in }, onPromote: { _, _ in }, onOpenRegion: { _ in }, selection: RegionSelection()
        )
        let window = NSWindow(contentRect: CGRect(origin: CGPoint(x: 100, y: 100), size: size),
                              styleMask: [.borderless], backing: .buffered, defer: false)
        let host = NSHostingView(rootView: layer.frame(width: size.width, height: size.height))
        window.contentView = host
        defer { window.contentView = nil }

        // The layer reads the feed in `.onChange`, which SwiftUI runs once per update with the LATEST
        // event: a press published in the same turn as the first drag is never seen, and no band begins.
        // Lay the layer out first, then let the press land (the band appears, empty) before dragging.
        host.layoutSubtreeIfNeeded()
        try await Task.sleep(nanoseconds: 50_000_000)
        feed.publish(PreviewPointerEvent(phase: .pressed, point: CGPoint(x: 0.1, y: 0.2), shift: false, clickCount: 1))
        try await settle(host) { !probe.frame.isNull }
        XCTAssertFalse(probe.frame.isNull, "the press began a band")

        for end in [CGPoint(x: 0.3, y: 0.35), CGPoint(x: 0.6, y: 0.5), CGPoint(x: 0.25, y: 0.8)] {
            feed.publish(PreviewPointerEvent(phase: .dragged, point: end, shift: false, clickCount: 1))
            // The overlay's own mapping of the rectangle dragged so far -- what the region will be.
            let want = try XCTUnwrap(BoundingBoxGeometry.viewRect(
                normalized: [Double(min(0.1, end.x)), Double(min(0.2, end.y)),
                             Double(abs(end.x - 0.1)), Double(abs(end.y - 0.2))],
                in: size, visible: CGRect(x: 0, y: 0, width: 1, height: 1)
            ))
            // SwiftUI applies the pointer on a later turn: wait for the band to reach this drag's size.
            try await settle(host) {
                abs(probe.frame.width - want.width) < 1 && abs(probe.frame.height - want.height) < 1
            }
            let drawn = probe.frame
            XCTAssertFalse(drawn.isNull, "the band is drawn")
            XCTAssertEqual(drawn.minX, want.minX, accuracy: 1, "the band starts where the press was, at \(end)")
            XCTAssertEqual(drawn.minY, want.minY, accuracy: 1, "not below it")
            XCTAssertEqual(drawn.width, want.width, accuracy: 1)
            XCTAssertEqual(drawn.height, want.height, accuracy: 1)
        }
    }

    /// Lay `host` out and yield until `done` holds, for at most a second.
    private func settle(_ host: NSView, until done: () -> Bool) async throws {
        for _ in 0..<100 {
            host.layoutSubtreeIfNeeded()
            if done() { return }
            try await Task.sleep(nanoseconds: 10_000_000)
        }
    }
}
#endif
