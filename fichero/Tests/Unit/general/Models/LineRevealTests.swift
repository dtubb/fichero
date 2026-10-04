@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// `reader.order.reveal-line-in-preview` (#5424): double-clicking a line in the Order tab or the
/// Order pane, or clicking a line in the Reader, reveals it in the linked Preview -- its box selected,
/// scrolled and zoomed to -- through ONE action, `WindowState.revealSegments`. Played over the recorded
/// engine answer for the imported Syriac page (the fixture `ImportedPageDrawsItsBoxesTests` uses),
/// through the real `SegmentStore`, `RegionSelection` and `WindowState`; only the HTTP transport is
/// stubbed. No click is driven: the surfaces' handlers are one-line calls into the action tested here.
@MainActor
@Suite(.serialized)
struct LineRevealTests {
    /// Answers every request to the test host with the recorded segments route.
    private final class RecordedPage: URLProtocol {
        nonisolated(unsafe) static var body = Data()
        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "127.0.0.1" }
        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            guard let url = request.url, let response = HTTPURLResponse(
                url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": "application/json"]
            ) else { return }
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Self.body)
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}
    }

    private func loadedStore() async throws -> SegmentStore {
        RecordedPage.body = try Data(contentsOf: AppSource.sibling("Tests")
            .appendingPathComponent("Fixtures/segments/syriac_onb-syr1-0001.route.json"))
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RecordedPage.self]
        let client = FicheroClient(
            baseURL: try #require(URL(string: "https://127.0.0.1:8765")),
            libraryPath: "/tmp/LineRevealTests.fichero",
            session: URLSession(configuration: configuration)
        )
        let store = SegmentStore(service: SegmentService(ficheroClient: client))
        await store.load(documentId: "doc-0001")
        return store
    }

    /// A window whose linked Preview is `preview` (the focused Source-view pane).
    private func window(linkedTo preview: RegionSelection) -> WindowState {
        let window = WindowState(libraryId: UUID())
        window.offerRegionSelection(preview)
        return window
    }

    /// WHY: the maintainer double-clicked lines in the Order tab and the Order pane on Mosquera and the
    /// Preview did not move. The reveal must select the line's box AND hand the Preview the line's rect
    /// to zoom to, and the Order list's double-click and the Reader's line click must produce the SAME
    /// reveal (target, rect, box) -- one action, so the surfaces cannot drift apart.
    @Test func orderListDoubleClickAndReaderLineClickMakeTheSameReveal() async throws {
        let store = try await loadedStore()
        let shown = try #require(SegmentDisplay.selected(for: "doc-0001", store: store))
        let line = try #require(store.segments(documentId: "doc-0001").first { $0.kind == "line" })
        let box = try #require(line.boxIndex)

        // The Order list's double-click (`ReadingOrderList.reveal`) on that line's row.
        let orderPreview = RegionSelection()
        let fromOrder = window(linkedTo: orderPreview).revealSegments([line.id], documentId: "doc-0001", store: store)

        // The Reader's click: the page's `lineFocused` message, as `focusLine` reads it.
        let focus = try #require(ReaderLineSelection.focus(from: ["pageId": "doc-0001", "segmentId": line.id]))
        let readerPreview = RegionSelection()
        let fromReader = window(linkedTo: readerPreview).revealSegments(
            [focus.segmentId], documentId: focus.pageId, store: store
        )

        #expect(fromOrder == [line.id])
        #expect(fromReader == fromOrder, "both surfaces reveal the same segment")
        #expect(orderPreview.resolvedIndices(in: shown.geometry.boxes) == [box], "the line's box is selected")
        #expect(readerPreview.resolvedIndices(in: shown.geometry.boxes) == [box])
        #expect(orderPreview.revealRect == shown.geometry.boxes[box].bbox, "the Preview zooms to the line's box")
        #expect(readerPreview.revealRect == orderPreview.revealRect, "to the same rect from either surface")
        #expect(orderPreview.revealCount == 1 && readerPreview.revealCount == 1)
    }

    /// WHY: a second double-click on the same line must zoom again (the person panned away), so the
    /// pane follows a count that moves on every reveal, not the rect, which did not change.
    @Test func revealingTheSameLineTwiceZoomsTwice() async throws {
        let store = try await loadedStore()
        let line = try #require(store.segments(documentId: "doc-0001").first { $0.kind == "line" })
        let preview = RegionSelection()
        let window = window(linkedTo: preview)
        window.revealSegments([line.id], documentId: "doc-0001", store: store)
        let rect = preview.revealRect
        window.revealSegments([line.id], documentId: "doc-0001", store: store)
        #expect(preview.revealCount == 2)
        #expect(preview.revealRect == rect)
    }

    /// WHY: with no Preview to reveal in, a double-click must do nothing at all -- never select into a
    /// stray selection nobody sees -- and a plain select (a single click) must never zoom.
    @Test func noLinkedPreviewRevealsNothingAndASelectNeverZooms() async throws {
        let store = try await loadedStore()
        let line = try #require(store.segments(documentId: "doc-0001").first { $0.kind == "line" })
        #expect(WindowState(libraryId: UUID()).revealSegments([line.id], documentId: "doc-0001", store: store).isEmpty)

        let preview = RegionSelection()
        InspectorPath.select(segmentIds: [line.id], into: preview, documentId: "doc-0001", store: store)
        #expect(!preview.isEmpty)
        #expect(preview.revealCount == 0 && preview.revealRect == nil)
    }

    /// WHY (#4981, applied to #5424): a reveal from the Inspector's own Order tab lights the box in the
    /// Preview but must not change the Inspector -- before this, the first click of the double-click
    /// swapped the Order tab for the line's inspector and the second click landed on nothing. The
    /// Reader's click is not the Inspector's own, so the Inspector follows it (#5155).
    @Test func aRevealFromTheInspectorsOrderTabLeavesTheInspectorWhereItWas() async throws {
        let store = try await loadedStore()
        let line = try #require(store.segments(documentId: "doc-0001").first { $0.kind == "line" && $0.parentSegmentId != nil })
        let block = try #require(line.parentSegmentId)
        let preview = RegionSelection()
        let window = window(linkedTo: preview)
        let inspectorSees = { InspectorPath.selectedSegmentIds(selection: preview, documentId: "doc-0001", store: store) }

        // The page-level Order tab ("Layout order"): the Inspector was on the page, and stays there.
        let wrote = window.revealSegments([line.id], documentId: "doc-0001", store: store)
        #expect(inspectorSees() == [line.id], "the linked Preview's selection is the line")
        let pageHold = InspectorPath.Hold(wrote: wrote, shown: [])
        #expect(InspectorPath.Hold.inspected(inspectorSees(), held: pageHold).isEmpty, "the Inspector stays on the page")

        // The Order section of a block's inspector: it stays on the block.
        let blockHold = InspectorPath.Hold(wrote: wrote, shown: [block])
        #expect(InspectorPath.Hold.inspected(inspectorSees(), held: blockHold) == [block])

        // The Reader's click (no hold) and any later selection are followed.
        #expect(InspectorPath.Hold.inspected(inspectorSees(), held: nil) == [line.id])
        InspectorPath.select(segmentIds: [block], into: preview, documentId: "doc-0001", store: store)
        #expect(InspectorPath.Hold.inspected(inspectorSees(), held: pageHold) == [block])
    }

    /// WHY: "one reveal action, shared by every surface" -- a surface that grew its own select-and-zoom
    /// would pass every test above and still drift. Each surface's handler must call the one action.
    @Test func everySurfaceCallsTheOneRevealAction() throws {
        #expect(try AppSource.code("Views/Components/ReadingOrderList.swift").contains("windowState.revealSegments("))
        #expect(try AppSource.code("Views/Reader/Knowledge/DocumentKGWebPaneCoordinatorMacOS.swift")
            .contains("windowState?.revealSegments("))
        #expect(try AppSource.code("Views/Preview/ImageViewer/ZoomableImagePreviewMac.swift")
            .contains("zoomToNormalizedRegion(rect)"))
    }
}
