@testable import Fichero
import FicheroAPIClient
import XCTest

/// `segment-editor.md` "Box colour and the segment hierarchy", ruled 2026-10-05: **A -- nested, inheriting,
/// lighter** (#5426; `source.editor.hierarchy.*`). Through the REAL path a page takes to the screen -- the
/// engine's segment listing into `SegmentStore`, the Preview's `SegmentDisplay.selected` (the boxes every overlay
/// draws), the Segments list's rows (`SegmentsPane.outline` over `workingSegments`) and the Reader's region rules
/// (`ReaderRegionRules.blocks`) -- not over boxes made by hand, because a box made by hand carries whatever
/// parent the test gives it and would pass while the store dropped it.
///
/// What breaks without these: a page with words loses its lines and regions again (the ladder drew only the
/// finest level), a word stops looking like its line's, a child outdraws its parent, the list goes back to one
/// level at a time, or selecting a region stops lighting what it holds.
@MainActor
final class SegmentHierarchyTests: XCTestCase {
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

    /// A nested page as the engine lists it, in as-written order: region r1 holding line l1 (words w1, w2) and
    /// line l2 (word w3); region r2 holding line l3. Or, `flat`, three lines and no parents at all.
    private func loadedPage(flat: Bool = false) async throws -> (store: SegmentStore, drawn: OCRGeometry) {
        let rows: [(id: String, kind: String, parent: String?)] = flat
            ? [("a", "line", nil), ("b", "line", nil), ("c", "line", nil)]
            : [("r1", "region", nil), ("l1", "line", "r1"), ("w1", "word", "l1"), ("w2", "word", "l1"),
               ("l2", "line", "r1"), ("w3", "word", "l2"), ("r2", "region", nil), ("l3", "line", "r2")]
        let json: [[String: Any]] = rows.enumerated().map { index, row in
            var segment: [String: Any] = [
                "id": row.id, "provisional": false, "document_id": "page-1", "pass_id": "pass-1",
                "kind": row.kind, "provenance_kind": "workflow", "box_index": index, "text": row.id,
                "anchor": ["document_id": "page-1", "rect": [0.1, 0.05 + Double(index) * 0.1, 0.5, 0.08]]
            ]
            if let parent = row.parent { segment["parent_segment_id"] = parent }
            return segment
        }
        OneAnswer.listing = try JSONSerialization.data(withJSONObject: [
            "document_id": "page-1",
            "passes": [["id": "pass-1", "provisional": false, "document_id": "page-1", "name": "transcription",
                        "provenance_kind": "workflow", "working": true, "drawn": true, "rank": 0]],
            "segments": json
        ])
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [OneAnswer.self]
        let client = FicheroClient(
            baseURL: URL(string: "https://127.0.0.1:8765")!,
            libraryPath: "/tmp/SegmentHierarchyTests.fichero",
            session: URLSession(configuration: configuration)
        )
        let store = SegmentStore(service: SegmentService(ficheroClient: client))
        await store.load(documentId: "page-1")
        let drawn = try XCTUnwrap(SegmentDisplay.selected(for: "page-1", store: store)?.geometry,
                                  "the Preview draws the store's pass")
        return (store, drawn)
    }

    private func box(_ id: String, in drawn: OCRGeometry) throws -> OCRGeometryBox {
        try XCTUnwrap(drawn.boxes.first { $0.segmentId == id }, "\(id) is drawn")
    }

    /// The overlay the image page builds from the drawn boxes (`ZoomableImagePreview.documentOverlay`'s
    /// mapping): the parent and the selection ride along.
    private func overlay(_ drawn: OCRGeometry, selecting ids: Set<String> = []) -> DocumentOverlay {
        DocumentOverlay(
            boxes: drawn.displayIndexedBoxes.map { entry in
                DocumentOverlay.Box(bbox: entry.box.bbox, confidence: entry.box.confidence,
                                    segmentId: entry.box.segmentId, kind: entry.box.level,
                                    parentSegmentId: entry.box.parentSegmentId, tone: entry.box.tone)
            },
            selectedSegmentIds: ids
        )
    }

    // MARK: - children-drawn-as-children

    /// "A finer level never hides its parents: a page with words still draws its lines and regions under them."
    func testAPageWithWordsStillDrawsItsLinesAndRegions() async throws {
        let drawn = try await loadedPage().drawn
        let shown = drawn.displayIndexedBoxes
        XCTAssertEqual(shown.map(\.index), Array(0..<8), "every box, at the engine's own index (curation's address)")
        XCTAssertEqual(Set(shown.map(\.box.level)), ["region", "line", "word"], "every level at once")
        XCTAssertEqual(shown.filter { $0.box.level == "line" }.map(\.box.segmentId), ["l1", "l2", "l3"])
        XCTAssertEqual(try box("w1", in: drawn).parentSegmentId, "l1", "the word knows its line on the drawn box")
        XCTAssertEqual(try box("l1", in: drawn).parentSegmentId, "r1")
    }

    /// "A child takes its parent's colour: a word takes its line's shade."
    func testAWordsToneIsItsLines() async throws {
        let drawn = try await loadedPage().drawn
        XCTAssertEqual(try box("w1", in: drawn).tone, try box("l1", in: drawn).tone)
        XCTAssertEqual(try box("w2", in: drawn).tone, try box("l1", in: drawn).tone)
        XCTAssertEqual(try box("w3", in: drawn).tone, try box("l2", in: drawn).tone)
        XCTAssertNotEqual(try box("l1", in: drawn).tone, try box("l2", in: drawn).tone, "the lines are graded")
    }

    /// "Each finer level draws INSIDE its parent and lighter than it", every parent-child pair on the page, at
    /// rest; and words are hairlines, thinner than the lines they sit in.
    func testEachChildIsDrawnLighterThanItsParent() async throws {
        let drawn = try await loadedPage().drawn
        let byId = Dictionary(uniqueKeysWithValues: drawn.boxes.compactMap { box in box.segmentId.map { ($0, box) } })
        func opacity(_ box: OCRGeometryBox) -> Double {
            SegmentHierarchy.strokeOpacity(level: .init(kind: box.level), toneStrength: box.tone?.strength ?? 1)
        }
        var pairs = 0
        for child in drawn.boxes {
            guard let parentId = child.parentSegmentId, let parent = byId[parentId] else { continue }
            XCTAssertLessThan(opacity(child), opacity(parent), "\(child.segmentId ?? "?") is lighter than \(parentId)")
            pairs += 1
        }
        XCTAssertEqual(pairs, 6, "every child on the page was compared")
        XCTAssertLessThan(SegmentHierarchy.widthFactor(.word), SegmentHierarchy.widthFactor(.line), "words are hairlines")
        XCTAssertGreaterThan(SegmentHierarchy.washOpacity(level: .region), 0, "a region is a faint wash of its hue")
        XCTAssertEqual(SegmentHierarchy.washOpacity(level: .line), 0, "only a region fills at rest")
    }

    /// With every level drawn, only the finest sets its reading inline: a line's reading drawn over its own
    /// words would set the page's text twice (#5411's overflow, one level down).
    func testOnlyTheFinestLevelSetsItsReadingInline() async throws {
        let drawn = try await loadedPage().drawn
        let finest = overlay(drawn).finestLevel
        XCTAssertEqual(finest, .word)
        XCTAssertTrue(DocumentOverlay.setsTextInline(kind: "word", finest: finest))
        XCTAssertFalse(DocumentOverlay.setsTextInline(kind: "line", finest: finest))
        XCTAssertFalse(DocumentOverlay.setsTextInline(kind: "region", finest: finest))
    }

    /// "Selecting a parent lights its children and dims what is outside it."
    func testSelectingARegionLightsItsChildren() async throws {
        let drawn = try await loadedPage().drawn
        let emphasis = overlay(drawn, selecting: ["r1"]).emphasis
        for id in ["l1", "l2", "w1", "w2", "w3"] {
            XCTAssertEqual(emphasis[id], .lit, "\(id), inside r1, is lit")
        }
        XCTAssertEqual(emphasis["r2"], .dimmed)
        XCTAssertEqual(emphasis["l3"], .dimmed, "outside the selection dims")
        let lit = try box("w1", in: drawn)
        XCTAssertGreaterThan(
            SegmentHierarchy.strokeOpacity(level: .word, toneStrength: lit.tone?.strength ?? 1, emphasis: .lit),
            SegmentHierarchy.strokeOpacity(level: .word, toneStrength: lit.tone?.strength ?? 1),
            "a lit child is drawn stronger than at rest"
        )
    }

    /// "Selecting a child shows its parent's outline at full strength."
    func testSelectingAWordShowsItsLineAndRegion() async throws {
        let drawn = try await loadedPage().drawn
        let emphasis = overlay(drawn, selecting: ["w1"]).emphasis
        XCTAssertEqual(emphasis["l1"], .parent)
        XCTAssertEqual(emphasis["r1"], .parent)
        XCTAssertEqual(emphasis["w2"], .dimmed, "a sibling is outside the selection")
        XCTAssertEqual(SegmentHierarchy.strokeOpacity(level: .line, toneStrength: 0.45, emphasis: .parent), 1,
                       "full strength, whatever its shade")
        XCTAssertTrue(overlay(drawn).emphasis.isEmpty, "nothing selected: every box at rest")
    }

    /// A flat pass: lines are the page's implicit region; selecting one lights nothing and shows no parent.
    func testAFlatPassHasNoParentsToShow() async throws {
        let drawn = try await loadedPage(flat: true).drawn
        XCTAssertTrue(drawn.boxes.allSatisfy { $0.parentSegmentId == nil })
        XCTAssertEqual(Set(drawn.boxes.compactMap(\.tone?.hue)), [0], "one implicit region, one hue")
        let emphasis = overlay(drawn, selecting: ["b"]).emphasis
        XCTAssertEqual(emphasis, ["a": .dimmed, "b": .rest, "c": .dimmed])
    }

    // MARK: - segments-list-nests

    /// "The Segments list groups rows by region: its lines indented under it, a line discloses its words", each
    /// level in the order the page reads it.
    func testTheListGroupsLinesUnderRegionsInReadingOrder() async throws {
        let store = try await loadedPage().store
        let segments = store.workingSegments(documentId: "page-1")
        let rows = SegmentsPane.outline(segments, top: SegmentsPane.asWritten(segments, under: nil))
        XCTAssertEqual(rows.map(\.segmentId), ["r1", "r2"])
        XCTAssertEqual(rows[0].children.map(\.segmentId), ["l1", "l2"], "r1's lines, in reading order")
        XCTAssertEqual(rows[0].children[0].children.map(\.segmentId), ["w1", "w2"], "l1 discloses its words")
        XCTAssertEqual(rows[0].children[1].children.map(\.segmentId), ["w3"])
        XCTAssertEqual(rows[1].children.map(\.segmentId), ["l3"])
        // Each row's swatch is the colour its box is drawn in: the same tones, from the same pass.
        let tones = RegionColours.tones(of: segments)
        let drawn = try XCTUnwrap(SegmentDisplay.selected(for: "page-1", store: store)?.geometry)
        for row in ["r1", "l1", "w1", "l3"] {
            XCTAssertEqual(tones[row], try box(row, in: drawn).tone, "\(row): the row's swatch is its box's colour")
        }
    }

    // MARK: - reader-shows-regions and the legend

    /// The Reader rules each region's block of lines in the region's hue, sent as the palette NAME (never RGB).
    func testTheReaderRulesEachRegionsLinesInItsHue() async throws {
        let (store, drawn) = try await loadedPage()
        let blocks = ReaderRegionRules.blocks(store.workingSegments(documentId: "page-1"))
        let r1 = try XCTUnwrap(try box("r1", in: drawn).tone), r2 = try XCTUnwrap(try box("r2", in: drawn).tone)
        XCTAssertEqual(blocks, [
            .init(segmentIds: ["l1", "l2"], hue: SelectionStyle.regionPaletteName(r1)),
            .init(segmentIds: ["l3"], hue: SelectionStyle.regionPaletteName(r2))
        ])
        XCTAssertEqual(SelectionStyle.regionPaletteNames.count, SelectionStyle.regionPalette.count,
                       "a name for every hue in the palette")
        let script = ReaderRegionRules.showRegionsScript(blocks)
        XCTAssertTrue(script.hasPrefix("window.fichero?.showRegions?.("), script)
        XCTAssertTrue(script.contains("\"hue\":\"blue\""), script)
    }

    /// The legend shows each region's hue once, in region reading order.
    func testTheLegendListsEachRegionsHueInOrder() async throws {
        let drawn = try await loadedPage().drawn
        XCTAssertEqual(RegionColours.legend(of: drawn.boxes.compactMap(\.tone)), [0, 1])
    }
}
