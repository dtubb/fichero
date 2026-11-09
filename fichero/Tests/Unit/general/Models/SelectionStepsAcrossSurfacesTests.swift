@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// #6457: Up/Down on the Inspector (or the Preview) step the ONE shared selection through the recorded Syriac page in reading order
/// through `InspectorPath.stepSelection`; Shift extends. Real `SegmentStore` and `RegionSelection`; only the HTTP transport is stubbed.
@MainActor
@Suite(.serialized)
struct SelectionStepsAcrossSurfacesTests {
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
            libraryPath: "/tmp/SelectionStepsAcrossSurfacesTests.fichero",
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

    @Test func downSelectsTheNextSegmentAndShiftExtends() async throws {
        let store = try await loadedStore()
        let order = try #require(SegmentDisplay.selected(for: "doc-0001", store: store)).geometry.boxes.compactMap(\.segmentId)
        try #require(order.count > 2)
        let selection = RegionSelection()
        InspectorPath.select(segmentIds: [order[0]], into: selection, documentId: "doc-0001", store: store)

        #expect(InspectorPath.stepSelection(by: 1, extend: false, selection: selection, documentId: "doc-0001", store: store))
        #expect(InspectorPath.selectedSegmentIds(selection: selection, documentId: "doc-0001", store: store) == [order[1]])

        #expect(InspectorPath.stepSelection(by: 1, extend: true, selection: selection, documentId: "doc-0001", store: store))
        #expect(Set(InspectorPath.selectedSegmentIds(selection: selection, documentId: "doc-0001", store: store)) == [order[1], order[2]])
    }

    @Test func upAtTheFirstSegmentMovesNothing() async throws {
        let store = try await loadedStore()
        let order = try #require(SegmentDisplay.selected(for: "doc-0001", store: store)).geometry.boxes.compactMap(\.segmentId)
        let selection = RegionSelection()
        InspectorPath.select(segmentIds: [order[0]], into: selection, documentId: "doc-0001", store: store)
        #expect(!InspectorPath.stepSelection(by: -1, extend: false, selection: selection, documentId: "doc-0001", store: store))
    }
}
