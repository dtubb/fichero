@testable import Fichero
import FicheroAPIClient
import XCTest

/// #5146, end to end: an imported page draws its boxes on the image.
///
/// The maintainer opened an imported Syriac page and saw its text with NO boxes on the image: the
/// page's one pass came from `format.import`, had no artifact type, and `rankedPasses` dropped it.
/// This plays the ENGINE'S OWN ANSWER for that page -- recorded by
/// `fichero-server/tests/unit/api/test_imported_page_draws_its_boxes.py`, which imports the real
/// PAGE file and re-checks the recording on every run -- through the exact calls the Mac canvas makes
/// (`loadOCRGeometry`: `SegmentStore.load`, then `SegmentDisplay.selected(for:store:)`). Only the
/// HTTP transport is stubbed. The boxes must be the file's 4 regions and 12 lines, as lxml read them.
@MainActor
final class ImportedPageDrawsItsBoxesTests: XCTestCase {
    /// Answers the segments list with the recorded engine answer; nothing else is served.
    private final class RecordedEngine: URLProtocol {
        nonisolated(unsafe) static var body = Data()

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.host == "127.0.0.1" && request.url?.path.hasPrefix("/api/segments/document/") == true
        }

        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            guard let url = request.url,
                  let response = HTTPURLResponse(
                      url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                      headerFields: ["Content-Type": "application/json"]
                  ) else {
                client?.urlProtocol(self, didFailWithError: URLError(.badURL))
                return
            }
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: Self.body)
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}
    }

    private struct ExpectedBox: Decodable {
        let level: String
        let bbox: [Double]
    }

    private func fixtures() throws -> URL {
        try AppSource.sibling("Tests").appendingPathComponent("Fixtures/segments")
    }

    /// The canvas's store, loaded from the recorded engine answer through the real service.
    private func loadedStore() async throws -> SegmentStore {
        RecordedEngine.body = try Data(contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.route.json"))
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RecordedEngine.self]
        let client = FicheroClient(
            baseURL: try XCTUnwrap(URL(string: "https://127.0.0.1:8765")),
            libraryPath: "/tmp/ImportedPageDrawsItsBoxesTests.fichero",
            session: URLSession(configuration: configuration)
        )
        let store = SegmentStore(service: SegmentService(ficheroClient: client))
        await store.load(documentId: "doc-0001")
        return store
    }

    /// #5152: the boxes drew but a click selected nothing, because a click needs a selection scope
    /// and the only one was the pass's ARTIFACT, which an imported pass does not have. This clicks a
    /// line the way `RegionInteractionLayer` does, then asks the Inspector's own resolution
    /// (`InspectorPath.selectedSegmentIds`, what `SourceSectionView` calls) what is selected.
    func testALineClickedOnTheImportedPageIsTheLineTheInspectorShows() async throws {
        let store = try await loadedStore()
        let selected = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        XCTAssertNil(selected.artifactId, "the imported pass has no artifact -- the case under test")
        let scope = try XCTUnwrap(
            SegmentDisplay.selectionScope(artifactId: selected.artifactId, passId: selected.passId),
            "an imported pass must still give a click something to select in"
        )
        let boxes = selected.geometry.boxes
        let lineIndex = try XCTUnwrap(boxes.firstIndex { $0.level == "line" })

        let selection = RegionSelection()
        selection.select(lineIndex, artifactId: scope, documentId: "doc-0001", in: boxes)
        let ids = InspectorPath.selectedSegmentIds(selection: selection, documentId: "doc-0001", store: store)

        let segments = store.segments(documentId: "doc-0001")
        let clicked = try XCTUnwrap(segments.first { $0.passId == selected.passId && $0.boxIndex == lineIndex })
        XCTAssertEqual(ids, [clicked.id])
        let path = try XCTUnwrap(InspectorPath.to(clicked.id, in: segments))
        XCTAssertEqual(path.crumbs.map(\.kind), ["region", "line"])
    }

    func testTheImportedSyriacPageDrawsTheFilesRegionsAndLines() async throws {
        let expected = try JSONDecoder().decode(
            [ExpectedBox].self,
            from: Data(contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.expected-boxes.json"))
        )
        let store = try await loadedStore()
        XCTAssertNil(store.loadError(documentId: "doc-0001"))
        let selected = try XCTUnwrap(
            SegmentDisplay.selected(for: "doc-0001", store: store),
            "the canvas's own call found nothing to draw for an imported page (#5146)"
        )

        let order: (String, [Double], String, [Double]) -> Bool = { lhsLevel, lhsBox, rhsLevel, rhsBox in
            lhsLevel != rhsLevel ? lhsLevel < rhsLevel : lhsBox.lexicographicallyPrecedes(rhsBox)
        }
        let drawn = selected.geometry.boxes.sorted { order($0.level, $0.bbox, $1.level, $1.bbox) }
        let want = expected.sorted { order($0.level, $0.bbox, $1.level, $1.bbox) }
        XCTAssertEqual(drawn.count, 16)
        XCTAssertEqual(drawn.map(\.level), want.map(\.level))
        for (box, file) in zip(drawn, want) {
            for (got, wanted) in zip(box.bbox, file.bbox) {
                XCTAssertEqual(got, wanted, accuracy: 2e-6, "\(box.level) box differs from the file")
            }
        }
    }
}
