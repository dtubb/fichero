@testable import Fichero
import FicheroAPIClient
import XCTest

/// `segment-editor.md` "Box colour and the segment hierarchy" (ruled 2026-10-04, #5426, #5463, #5467 part b),
/// through the REAL path a page takes to the screen: the engine's segment listing into `SegmentStore`, the
/// Preview's `SegmentDisplay.selected` (the boxes the overlay draws), and the Inspector's row lookup
/// (`RegionColours.tone(of:drawnIn:)`), each turned into a colour by `SelectionStyle.regionColour`. What breaks
/// without these: the Inspector's swatch and the Preview's box disagree about the same line (two colour paths),
/// a region-less line gets a hashed colour of its own, or the store's page loses its order on the way.
@MainActor
final class BoxColourThroughTheStoreTests: XCTestCase {
    /// One canned answer for the page's segment listing; every other request gets `{}`.
    private final class OneAnswer: URLProtocol {
        nonisolated(unsafe) static var listing = Data()

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "127.0.0.1" }
        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            guard let url = request.url,
                  let response = HTTPURLResponse(url: url, statusCode: 200, httpVersion: "HTTP/1.1",
                                                 headerFields: ["Content-Type": "application/json"]) else {
                client?.urlProtocol(self, didFailWithError: URLError(.badURL))
                return
            }
            let body = url.path.contains("/api/segments/document/") ? Self.listing : Data("{}".utf8)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: body)
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}
    }

    override func setUp() {
        super.setUp()
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
    }

    /// A page as the engine lists it: region r1 with lines l1, l2; region r2 with line l3; and two lines
    /// with no region, a and b. Box order is the as-written order.
    private func loadedPage() async throws -> (store: SegmentStore, drawn: OCRGeometry) {
        // id: parent ("" for none); kind is "region" for r*, "line" otherwise.
        let segments: KeyValuePairs<String, String> = ["r1": "", "l1": "r1", "l2": "r1", "r2": "", "l3": "r2", "a": "", "b": ""]
        var json: [[String: Any]] = []
        for (index, segment) in segments.enumerated() {
            var row: [String: Any] = [
                "id": segment.key, "provisional": false, "document_id": "page-1", "pass_id": "pass-1",
                "kind": segment.key.hasPrefix("r") ? "region" : "line", "provenance_kind": "workflow",
                "box_index": index, "text": segment.key,
                "anchor": ["document_id": "page-1", "rect": [0.1, 0.05 + Double(index) * 0.1, 0.5, 0.08]]
            ]
            if !segment.value.isEmpty { row["parent_segment_id"] = segment.value }
            json.append(row)
        }
        OneAnswer.listing = try JSONSerialization.data(withJSONObject: [
            "document_id": "page-1",
            "passes": [["id": "pass-1", "provisional": false, "document_id": "page-1",
                        "name": "transcription", "provenance_kind": "workflow"]],
            "segments": json
        ])
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [OneAnswer.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/BoxColourThroughTheStoreTests.fichero",
            session: URLSession(configuration: configuration)
        )
        let store = SegmentStore(service: SegmentService(ficheroClient: client))
        await store.load(documentId: "page-1")
        let drawn = try XCTUnwrap(SegmentDisplay.selected(for: "page-1", store: store)?.geometry,
                                  "the Preview draws the store's pass")
        return (store, drawn)
    }

    private func tone(_ id: String, in drawn: OCRGeometry) -> RegionColours.Tone? {
        drawn.boxes.first { $0.segmentId == id }?.tone
    }

    /// `source.editor.colour.region-hue` + `reading-order-gradient`, on the boxes the Preview draws.
    func testThePreviewsBoxesTakeTheirRegionsHueShadedInOrder() async throws {
        let drawn = try await loadedPage().drawn
        let first = try XCTUnwrap(tone("l1", in: drawn)), second = try XCTUnwrap(tone("l2", in: drawn))
        let otherRegion = try XCTUnwrap(tone("l3", in: drawn))
        XCTAssertEqual(first.hue, second.hue, "lines of one region share its hue")
        XCTAssertNotEqual(first.hue, otherRegion.hue, "two regions never share a hue")
        XCTAssertGreaterThan(first.strength, second.strength, "the first line in reading order is the stronger")
        XCTAssertNotEqual(SelectionStyle.regionColour(first), SelectionStyle.regionColour(otherRegion))
    }

    /// `source.editor.colour.never-random` + `regionless-lines-are-one-region`: the page's two loose lines are
    /// one hue, the next after the regions, graded -- never a colour keyed by their own ids.
    func testRegionlessLinesAreThePagesOneRegion() async throws {
        let drawn = try await loadedPage().drawn
        let looseA = try XCTUnwrap(tone("a", in: drawn)), looseB = try XCTUnwrap(tone("b", in: drawn))
        XCTAssertEqual(looseA.hue, looseB.hue, "one implicit region, one hue")
        XCTAssertEqual(looseA.hue, 2, "placed after r1 and r2, where its first line falls")
        XCTAssertGreaterThan(looseA.strength, looseB.strength)
        let again = try await loadedPage().drawn
        XCTAssertEqual(drawn.boxes.map(\.tone), again.boxes.map(\.tone), "the same page draws the same colours every time")
    }

    /// #5467 part b: the Inspector's row for a line (listed from the ARTIFACT's boxes, which carry no region)
    /// shows the colour the Preview draws that line in, from the same function.
    func testTheInspectorRowSwatchIsThePreviewBoxColour() async throws {
        let drawn = try await loadedPage().drawn
        for box in drawn.boxes {
            // The artifact's own copy of the box: same place, words and level, no tone.
            let artifactRow = OCRGeometryBox(text: box.text, bbox: box.bbox, level: box.level, confidence: box.confidence)
            let rowTone = RegionColours.tone(of: artifactRow, drawnIn: drawn)
            XCTAssertNotNil(rowTone, "\(box.segmentId ?? "?") has a row colour")
            XCTAssertEqual(rowTone, box.tone, "\(box.segmentId ?? "?"): the row's tone is the box's")
            XCTAssertEqual(SelectionStyle.regionColour(rowTone), SelectionStyle.regionColour(box.tone))
        }
        XCTAssertNil(RegionColours.tone(of: OCRGeometryBox(text: "x", bbox: [0, 0, 1, 1], level: "line", confidence: nil),
                                        drawnIn: drawn),
                     "a row the Preview does not draw has no region colour (it draws plain)")
    }
}
