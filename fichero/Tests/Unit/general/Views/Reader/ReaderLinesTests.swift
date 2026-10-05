import AppKit
@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The Reader's Lines mode and the Preview's double-click popover (#5414): `reader.lines.image-above-text`,
/// `reader.lines.edit-saves-a-persons-reading`, `reader.lines.zoom-scales-together`,
/// `reader.lines.follow-direction`, `preview.segment.double-click-popover`. Played over the recorded engine
/// answer for the imported Syriac page (the fixture `LineRevealTests` uses), through the real
/// `SegmentStore`, `SegmentService`, `ReaderTextEditRunner` and `RegionSelection`; only the HTTP transport
/// is stubbed, and it records what the app asked for. No row is rendered: the rows read these answers.
@MainActor
@Suite(.serialized, .tags(.reader))
struct ReaderLinesTests {
    /// Answers every request to the test host, recording the pictures asked for and the actions invoked.
    private final class RecordedEngine: URLProtocol {
        nonisolated(unsafe) static var route = Data()
        nonisolated(unsafe) static var text = Data()
        nonisolated(unsafe) static var readings = Data()
        nonisolated(unsafe) static var picture = Data()
        nonisolated(unsafe) static var pictures: [String] = []
        nonisolated(unsafe) static var invoked: [Data] = []

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "127.0.0.1" }
        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
        override func startLoading() {
            guard let url = request.url else { return }
            let path = url.path
            var body = Self.route
            var type = "application/json"
            if path.hasSuffix("/picture") {
                Self.pictures.append("\(path)?\(url.query ?? "")")
                body = Self.picture
                type = "image/png"
            } else if path.hasSuffix("/readings") {
                body = Self.readings
            } else if path.hasSuffix("/text") {
                body = Self.text
            } else if path == "/api/actions/invoke" {
                Self.invoked.append(Self.bodyOf(request))
                let audit = "audit-\(Self.invoked.count)"
                body = Data(#"{"ok":true,"result":{"id":"rep-0009"},"audit_id":"\#(audit)","changed_domains":["segment"]}"#.utf8)
            }
            guard let response = HTTPURLResponse(
                url: url, statusCode: 200, httpVersion: "HTTP/1.1", headerFields: ["Content-Type": type]
            ) else { return }
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: body)
            client?.urlProtocolDidFinishLoading(self)
        }
        override func stopLoading() {}

        private static func bodyOf(_ request: URLRequest) -> Data {
            if let body = request.httpBody { return body }
            guard let stream = request.httpBodyStream else { return Data() }
            stream.open()
            defer { stream.close() }
            var data = Data()
            var buffer = [UInt8](repeating: 0, count: 4096)
            while true {
                let read = stream.read(&buffer, maxLength: buffer.count)
                guard read > 0 else { break }
                data.append(buffer, count: read)
            }
            return data
        }
    }

    private let documentId = "doc-0001"
    /// The recorded page's lines, in the engine's order: twelve lines in four regions.
    private let lineIds = (3...14).map { String(format: "seg-%04d", $0) }

    private func fixture(_ name: String) throws -> Data {
        try Data(contentsOf: AppSource.sibling("Tests").appendingPathComponent("Fixtures/segments/\(name)"))
    }

    /// The page's text answer with the first line written top to bottom and the second right to left:
    /// the recorded Syriac page's own answer, its blocks replaced by these two.
    private func textAnswer() throws -> Data {
        var text = try #require(JSONSerialization.jsonObject(with: fixture("syriac_onb-syr1-0001.page-text.json")) as? [String: Any])
        func block(_ region: String, _ line: String, _ direction: String) -> [String: Any] {
            ["region_segment_id": region, "direction": direction, "direction_level": NSNull(), "text": "x",
             "spans": [["segment_id": line, "representation_id": "rep-x", "start": 0, "end": 1]]]
        }
        text["blocks"] = [block("seg-0016", "seg-0003", "ttb"), block("seg-0016", "seg-0004", "rtl")]
        return try JSONSerialization.data(withJSONObject: text)
    }

    private func png() throws -> Data {
        let rep = try #require(NSBitmapImageRep(
            bitmapDataPlanes: nil, pixelsWide: 60, pixelsHigh: 10, bitsPerSample: 8, samplesPerPixel: 4,
            hasAlpha: true, isPlanar: false, colorSpaceName: .deviceRGB, bytesPerRow: 0, bitsPerPixel: 0
        ))
        return try #require(rep.representation(using: .png, properties: [:]))
    }

    private struct Loaded {
        let store: SegmentStore
        let service: SegmentService
        let client: FicheroClient
    }

    private func loaded() async throws -> Loaded {
        RecordedEngine.route = try fixture("syriac_onb-syr1-0001.route.json")
        RecordedEngine.text = try textAnswer()
        RecordedEngine.readings = try fixture("syriac_onb-syr1-0001.first-line-readings.json")
        RecordedEngine.picture = try png()
        RecordedEngine.pictures = []
        RecordedEngine.invoked = []
        setenv("FICHERO_AUTH_TOKEN", "test-token", 1)
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [RecordedEngine.self]
        let client = FicheroClient(
            baseURL: try #require(URL(string: "https://127.0.0.1:8765")),
            libraryPath: "/tmp/ReaderLinesTests.fichero",
            session: URLSession(configuration: configuration)
        )
        let service = SegmentService(ficheroClient: client)
        let store = SegmentStore(service: service)
        await store.load(documentId: documentId)
        return Loaded(store: store, service: service, client: client)
    }

    private func line(_ id: String, in store: SegmentStore) throws -> Segment {
        try #require(store.segments(documentId: documentId).first { $0.id == id })
    }

    /// WHY (`reader.lines.image-above-text`): the maintainer asked to read a page line by line, each
    /// line's hand above its words. The rows must be the working pass's LINES -- not its regions -- in
    /// the page's order; each row must cut ITS OWN line from the page (the Segments grid's picture
    /// service, at a size that stays sharp when zoomed) and show the reading that COUNTS, not a stale
    /// one. And the mode follows the Preview's selection: a selected line is lit, a region is not a row.
    @Test func rowsAreThePagesLinesInOrderEachWithItsPictureAndTheReadingThatCounts() async throws {
        let page = try await loaded()
        let store = page.store, service = page.service
        let lines = ReaderLines.lines(documentId: documentId, store: store)
        #expect(lines.map(\.id) == lineIds, "the working pass's lines, in the engine's order, no regions")

        let editor = ReaderLineEditor(segment: try line("seg-0003", in: store))
        await editor.load(service)
        #expect(editor.picture != nil, "the line's picture, cut from the page")
        #expect(RecordedEngine.pictures == ["/api/segments/seg-0003/picture?size=\(ReaderLines.pictureSize)"])
        let readings = try #require(try await service.readings(segmentId: "seg-0003"))
        #expect(editor.reading?.id == "rep-0002", "the reading that counts (a person's correction)")
        #expect(editor.draft == readings.countingContent(ofKind: "transcription"))
        #expect(!editor.isChanged)

        let preview = RegionSelection()
        InspectorPath.select(segmentIds: ["seg-0005", "seg-0015"], into: preview, documentId: documentId, store: store)
        let selected = InspectorPath.selectedSegmentIds(selection: preview, documentId: documentId, store: store)
        #expect(ReaderLines.shown(selected, among: lines, segments: store.segments(documentId: documentId)) == ["seg-0005"])
    }

    /// WHY (`reader.lines.edit-saves-a-persons-reading`): a correction typed under a line must be a
    /// PERSON'S reading through the Inspector's own save -- one path -- so it is the Reader's
    /// `representation.create`, correcting the reading shown and refused if another counts now. A second
    /// path would write readings the stale check never sees. The row's request and the Inspector's must
    /// be the same request.
    @Test func anEditSavesThroughTheInspectorsSaveAsAPersonsReading() async throws {
        let page = try await loaded()
        let store = page.store, service = page.service, client = page.client
        let runner = ReaderTextEditRunner(
            actionsService: ActionsService(client: client), segmentService: service, undoManager: nil, refreshPage: { _ in }
        )
        let editor = ReaderLineEditor(segment: try line("seg-0003", in: store))
        await editor.load(service)
        editor.draft = "ܐܒܪܗܡ ܐܘܠܕ"
        #expect(editor.isChanged)
        await editor.save(runner: runner, service: service)
        #expect(editor.note == nil, "saved")

        let reading = try #require(try await service.readings(segmentId: "seg-0003")?.countingReading(ofKind: "transcription"))
        _ = await InspectorReadingEdit.save(
            "ܐܒܪܗܡ ܐܘܠܕ", documentId: documentId, segmentId: "seg-0003", editing: reading, runner: runner
        )
        let sent = try RecordedEngine.invoked.map { try #require(JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
        #expect(sent.compactMap { $0["name"] as? String } == ["representation.create", "representation.create"])
        let params = sent.compactMap { $0["params"] as? [String: Any] }
        let row = try #require(params.first)
        #expect(row["segment_id"] as? String == "seg-0003")
        #expect(row["document_id"] as? String == documentId)
        #expect(row["content"] as? String == "ܐܒܪܗܡ ܐܘܠܕ")
        #expect(row["kind"] as? String == "transcription")
        #expect(row["corrects_representation_id"] as? String == "rep-0002", "a correction OF the reading shown")
        #expect(row["expected_counting_id"] as? String == "rep-0002", "refused if another reading counts now")
        #expect(NSDictionary(dictionary: row) == NSDictionary(dictionary: try #require(params.last)),
                "the row's request IS the Inspector's")

        // Unchanged words write nothing.
        editor.revert()
        await editor.save(runner: runner, service: service)
        #expect(RecordedEngine.invoked.count == 2)
    }

    /// WHY (`reader.lines.zoom-scales-together`): zooming must grow the hand and the words together, and
    /// at every zoom the Reader offers (50%-300%) the picture must be drawn larger than its words, or the
    /// hand cannot be read against them. The popover shows the hand larger than the 100% row.
    @Test func zoomScalesPictureAndWordsTogetherWithThePictureAlwaysLarger() {
        let base = ReaderLines.Metrics(zoom: 1, bodySize: 13)
        let doubled = ReaderLines.Metrics(zoom: 2, bodySize: 13)
        #expect(doubled.fontSize == base.fontSize * 2)
        #expect(doubled.pictureExtent == base.pictureExtent * 2)
        for zoom in stride(from: 0.5, through: 3.0, by: 0.1) {
            let metrics = ReaderLines.Metrics(zoom: zoom)
            #expect(metrics.pictureExtent > metrics.fontSize, "at \(zoom) the picture is larger than the words")
        }
        #expect(ReaderLines.popoverZoom > 1)
    }

    /// WHY (`reader.lines.follow-direction`): a vertical line's picture is a tall strip; stacked above
    /// its words it would push them a page away. Its strip must stand BESIDE its column, and the
    /// direction must be the engine's cascade as the store resolves it, the same reading the Inspector's
    /// editor lays out by -- a right-to-left line still reads picture above words.
    @Test func aVerticalLineStandsBesideItsWordsFromTheResolvedDirection() async throws {
        let store = try await loaded().store
        #expect(store.direction(of: "seg-0003", documentId: documentId) == "ttb")
        #expect(ReaderLines.arrangement(direction: store.direction(of: "seg-0003", documentId: documentId)) == .beside)
        #expect(ReaderLines.arrangement(direction: store.direction(of: "seg-0004", documentId: documentId)) == .above)
        #expect(ReaderLines.arrangement(direction: "btt") == .beside)
        #expect(ReaderLines.arrangement(direction: nil) == .above, "no direction: written across")
    }

    /// WHY (`preview.segment.double-click-popover`): double-clicking a line, word or region box in the
    /// Preview must open that segment's popover, and the popover must BE the Lines mode's row -- the same
    /// view, the same segment, the same save -- at a larger zoom. A box naming no stored segment (a
    /// `legacy:` id cannot be saved to) keeps the double-click's old open/zoom.
    @Test func aDoubleClickedBoxOpensTheLinesModesRowForItsSegment() async throws {
        let store = try await loaded().store
        let boxes = try #require(SegmentDisplay.selected(for: documentId, store: store)).geometry.boxes
        let lineBox = try #require(boxes.first { $0.segmentId == "seg-0003" })
        let target = try #require(SegmentPopoverTarget.target(for: lineBox))
        #expect(target.id == "seg-0003")
        #expect(target.bbox == lineBox.bbox, "the popover points at the box double-clicked")

        let row: ReaderLineRow = try #require(ReaderLinePopover.row(segmentId: target.id, documentId: documentId, store: store))
        let expected = try line("seg-0003", in: store)
        #expect(row.segment == expected, "the Lines row for that segment")
        #expect(row.zoom == ReaderLines.popoverZoom)
        #expect(row.direction == store.direction(of: "seg-0003", documentId: documentId))

        if let regionBox = boxes.first(where: { $0.segmentId == "seg-0015" }) {
            #expect(SegmentPopoverTarget.target(for: regionBox)?.id == "seg-0015", "a region box opens one too")
        }
        var legacy = lineBox
        legacy.segmentId = "legacy:art-1:0"
        #expect(SegmentPopoverTarget.target(for: legacy) == nil)
        legacy.segmentId = nil
        #expect(SegmentPopoverTarget.target(for: legacy) == nil)
    }
}
