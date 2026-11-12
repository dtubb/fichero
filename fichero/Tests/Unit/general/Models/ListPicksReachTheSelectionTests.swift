@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

// Spec: source.editor.order-list-selection-shows-everywhere (#6476), source/segment-editor-crud.md.
//
// A row picked in the Segments pane never lit its box in the Preview or showed in the Inspector.
// The list wrote the pick as `onSelected?(InspectorPath.select(...))`; the Segments pane gives no
// `onSelected`, and an optional call with no callback never evaluates its argument, so the shared
// selection was never written. The write is `InspectorPath.selectListPicks` now, run before the
// callback. Real `SegmentStore` and `RegionSelection` over the recorded Syriac page; only HTTP is stubbed.

@MainActor
@Suite(.serialized)
struct ListPicksReachTheSelectionTests {
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
            libraryPath: "/tmp/ListPicksReachTheSelectionTests.fichero",
            session: URLSession(configuration: configuration)
        )
        let store = SegmentStore(service: SegmentService(ficheroClient: client))
        await store.load(documentId: "doc-0001")
        return store
    }

    @Test("a list's pick becomes the shared selection, read back by the Inspector, with no callback given")
    func pickIsTheSharedSelection() async throws {
        let store = try await loadedStore()
        let order = try #require(SegmentDisplay.selected(for: "doc-0001", store: store)).geometry.boxes.compactMap(\.segmentId)
        try #require(order.count > 3)
        let window = WindowState(libraryId: UUID())

        let chosen = InspectorPath.selectListPicks(
            [order[2]], order: order, into: window.sharedRegionSelection, documentId: "doc-0001", store: store
        )

        #expect(chosen == [order[2]])
        let read = InspectorPath.selectedSegmentIds(selection: window.sharedRegionSelection, documentId: "doc-0001", store: store)
        #expect(read == [order[2]])
    }

    @Test("several picks are written in the list's order, whatever order the set gives")
    func picksInTheListsOrder() async throws {
        let store = try await loadedStore()
        let order = try #require(SegmentDisplay.selected(for: "doc-0001", store: store)).geometry.boxes.compactMap(\.segmentId)
        try #require(order.count > 3)
        let selection = RegionSelection()

        let chosen = InspectorPath.selectListPicks(
            [order[3], order[1]], order: order, into: selection, documentId: "doc-0001", store: store
        )

        #expect(chosen == [order[1], order[3]])
    }
}
