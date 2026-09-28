@testable import Fichero
import SwiftUI
import XCTest

@MainActor
final class SegmentsPaneHostingTests: XCTestCase {
    /// The Segments pane spun forever in Daniel's morning build (2026-09-28): the library window's tree
    /// (`LibraryWorkspaceRoot`) injected its own hand-copied service list, which had no ReadingOrderService
    /// (nor SegmentService, RenditionService, APIClient), and the pane -- hosted in that tree -- makes its
    /// order store from that service. Hosted here in EXACTLY that tree's environment
    /// (`LibraryTreeEnvironment`, the root's own modifier), a view gets both services, so the pane goes
    /// on from loading; and a pane in a window without the service says so instead of spinning
    /// (`SegmentsPane.listState`). Breaks if the tree's list drifts from the shared one again, or the
    /// pane can wait on a service that will never come.
    func testTheSegmentsPaneInTheLibraryWindowsTreeGetsItsOrderServiceAndNeverSpinsForever() {
        final class Seen { var order = false; var segments = false }
        struct Probe: View {
            let seen: Seen
            @Environment(ReadingOrderService.self) private var order: ReadingOrderService?
            @Environment(SegmentService.self) private var segments: SegmentService?
            var body: some View {
                seen.order = order != nil
                seen.segments = segments != nil
                return Color.clear
            }
        }
        let seen = Seen()
        let library = LibraryPreviewFixtures.library
        let host = NSHostingView(rootView: Probe(seen: seen).modifier(LibraryTreeEnvironment(
            library: library, windowState: WindowState(libraryId: library.id), executionObserver: WorkflowExecutionObserver()
        )))
        host.frame = CGRect(x: 0, y: 0, width: 80, height: 80)
        host.layoutSubtreeIfNeeded()
        XCTAssertTrue(seen.order, "the pane's order service reaches the library window's tree")
        XCTAssertTrue(seen.segments)

        XCTAssertEqual(SegmentsPane.listState(hasDocument: true, hasOrders: false, hasOrderService: true), .loading)
        XCTAssertEqual(SegmentsPane.listState(hasDocument: true, hasOrders: true, hasOrderService: true), .list)
        XCTAssertEqual(SegmentsPane.listState(hasDocument: true, hasOrders: false, hasOrderService: false), .unavailable,
                       "no service: said, never a spinner with nothing coming")
        XCTAssertEqual(SegmentsPane.listState(hasDocument: false, hasOrders: false, hasOrderService: false), .noPage)
    }
}
