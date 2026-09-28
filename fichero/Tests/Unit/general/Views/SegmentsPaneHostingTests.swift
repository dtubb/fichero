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
        final class Seen {
            var order: ReadingOrderService?
            var segments: SegmentService?
            var renditions: RenditionService?
            var client: APIClient?
        }
        // Reads the four services the tree's old copy lacked, as the Segments pane (ReadingOrderService),
        // the image and PDF previews (SegmentService: no boxes in Daniel's build), the document canvas and
        // ContentView's renditions (RenditionService) and the activity and automation views (APIClient) do.
        struct Probe: View {
            let seen: Seen
            @Environment(ReadingOrderService.self) private var order: ReadingOrderService?
            @Environment(SegmentService.self) private var segments: SegmentService?
            @Environment(RenditionService.self) private var renditions: RenditionService?
            @Environment(APIClient.self) private var client: APIClient?
            var body: some View {
                seen.order = order
                seen.segments = segments
                seen.renditions = renditions
                seen.client = client
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
        XCTAssertTrue(seen.order === library.readingOrderService, "the Segments pane's order service reaches the tree")
        XCTAssertTrue(seen.segments === library.segmentService,
                      "the previews' SegmentService is the library's -- the one SegmentStore.shared(for:) keys the boxes by")
        XCTAssertTrue(seen.renditions === library.renditionService)
        XCTAssertTrue(seen.client === library.apiClient)

        XCTAssertEqual(SegmentsPane.listState(hasDocument: true, hasOrders: false, hasOrderService: true), .loading)
        XCTAssertEqual(SegmentsPane.listState(hasDocument: true, hasOrders: true, hasOrderService: true), .list)
        XCTAssertEqual(SegmentsPane.listState(hasDocument: true, hasOrders: false, hasOrderService: false), .unavailable,
                       "no service: said, never a spinner with nothing coming")
        XCTAssertEqual(SegmentsPane.listState(hasDocument: false, hasOrders: false, hasOrderService: false), .noPage)
    }
}
