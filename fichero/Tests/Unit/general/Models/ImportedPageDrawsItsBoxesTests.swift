@testable import Fichero
import CryptoKit
import FicheroAPIClient
import PDFKit
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
    /// Answers the segments list with the recorded engine answer, and RECORDS what the app sends to
    /// create an annotation (answered 422: the request is what is under test, not the reply).
    private final class RecordedEngine: URLProtocol {
        nonisolated(unsafe) static var body = Data()
        nonisolated(unsafe) static var annotationRequests: [Data] = []
        /// Every audited action the app invoked (`POST /api/actions/invoke`) and every audit row it
        /// asked to undo, in order -- answered as the engine would, with a fresh audit id.
        nonisolated(unsafe) static var invoked: [Data] = []
        nonisolated(unsafe) static var undone: [String] = []
        /// What `POST /api/actions/invoke` answers with; 409 is the engine's stale refusal (#5001).
        nonisolated(unsafe) static var invokeStatus = 200
        /// The engine out of reach for an invoke: the transport fails, no answer at all (13b out of reach).
        nonisolated(unsafe) static var invokeUnreachable = false
        /// The `result` an invoke answers with (the engine's is per action; `{}` unless a test says).
        nonisolated(unsafe) static var invokeResult = "{}"

        /// EVERY request to the test host is answered here, never only a list of paths: a path left
        /// off a list went to the real network (the versions and resolve calls, 2026-09-28), so a
        /// passing run depended on an engine happening to be up. A path with no branch below gets the
        /// recorded route's answer, which the test asserting on it will not mistake for its own.
        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool {
            request.url?.host == "127.0.0.1"
        }

        /// What `GET /api/hands` and `GET /api/hands/segment/{id}` answer (set by the test that asks).
        nonisolated(unsafe) static var handsReply = Data()
        nonisolated(unsafe) static var attributionsReply = Data()

        /// What `GET /api/source-settings/resolve` answers (set by the test that asks).
        nonisolated(unsafe) static var settingsReply = Data()

        /// What `GET /api/segments/document/{id}/matches` answers, and the query it was asked (#5165).
        nonisolated(unsafe) static var matchesReply = Data()
        nonisolated(unsafe) static var matchesQuery: String?
        /// What `GET /api/segments/{id}/versions` answers (#5163).
        nonisolated(unsafe) static var versionsReply = Data()
        /// What `GET /api/segments/{id}/readings` answers (set by the test that asks).
        nonisolated(unsafe) static var readingsReply = Data()

        /// What `GET /api/segments/passes/{id}/original` answers (set by the test that asks).
        nonisolated(unsafe) static var originalReply = Data()

        /// What `GET /api/editorial/segment/{id}` answers (set by the test that asks).
        nonisolated(unsafe) static var editorialReply = Data()

        /// What `/api/signs`, `/api/signs/{id}/instances`, `/api/letterforms/segment/{id}` and
        /// `/api/letterforms/allographs` answer (set by the test that asks).
        nonisolated(unsafe) static var signsReply = Data()
        nonisolated(unsafe) static var instancesReply = Data()
        nonisolated(unsafe) static var letterformReply = Data()
        nonisolated(unsafe) static var allographsReply = Data()

        /// What `/api/links/of/{id}`, `/api/links/types` and `/api/segments/{id}/reference` answer.
        nonisolated(unsafe) static var linksReply = Data()
        nonisolated(unsafe) static var linkTypesReply = Data()
        nonisolated(unsafe) static var referenceReply = Data()
        /// What `GET /api/rights/effective` answers.
        nonisolated(unsafe) static var rightsReply = Data()
        /// What `GET /api/segments/{id}/statements` answers.
        nonisolated(unsafe) static var statementsReply = Data()
        /// What the reading-order routes answer: the page's orders, the top level, one region's
        /// children (for `parent_entry_id` = `childrenOf`); every place POST is recorded.
        nonisolated(unsafe) static var ordersReply = Data()
        /// What `GET /api/formats` and `GET /api/documents/{id}/export/{format}` answer, and the
        /// export's path and query (#5162).
        nonisolated(unsafe) static var formatsReply = Data()
        nonisolated(unsafe) static var exportReply = Data()
        nonisolated(unsafe) static var exportRequest: (path: String, query: String?)?
        /// What `POST /api/locations/resolve` answers, and the body it was sent (#5164).
        nonisolated(unsafe) static var resolveReply = Data()
        nonisolated(unsafe) static var resolveRequests: [Data] = []
        /// What `GET /api/reading-orders/flows/onto/{page}` answers (#5160 residue).
        nonisolated(unsafe) static var flowsOntoReply = Data()
        /// What `GET /api/reading-orders/{id}/neighbours` answers, and the query it was asked (#5160).
        nonisolated(unsafe) static var neighboursReply = Data()
        nonisolated(unsafe) static var neighboursQuery: String?
        nonisolated(unsafe) static var topEntriesReply = Data()
        nonisolated(unsafe) static var childEntriesReply = Data()
        nonisolated(unsafe) static var childrenOf = ""
        nonisolated(unsafe) static var placed: [Data] = []
        /// What `GET /api/hands/{id}/attributions` answers, and `GET /api/segments/{id}` per id.
        nonisolated(unsafe) static var everythingReply = Data()
        nonisolated(unsafe) static var segmentReplies: [String: Data] = [:]
        /// What `GET /api/segments/{id}/picture` answers: the engine's PNG bytes, as image/png.
        nonisolated(unsafe) static var pictureReply = Data()

        private static func actionReply(auditId: String) -> Data {
            Data(#"{"ok":true,"result":{},"audit_id":"\#(auditId)","changed_domains":["segment"]}"#.utf8)
        }

        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            let path = request.url?.path ?? ""
            if Self.invokeUnreachable, path == "/api/actions/invoke" {
                client?.urlProtocol(self, didFailWithError: URLError(.cannotConnectToHost))
                return
            }
            let isAnnotation = path == "/api/annotations"
            // Only a CREATE is what is under test: a GET that re-reads the list has no body, and
            // recording it made the highlight test parse empty data when a store reloaded.
            if isAnnotation, request.httpMethod == "POST" { Self.annotationRequests.append(Self.bodyOf(request)) }
            var actionBody: Data?
            let isPicture = path.hasPrefix("/api/segments/") && path.hasSuffix("/picture")
            if isPicture {
                actionBody = Self.pictureReply
            } else if path.hasPrefix("/api/hands/"), path.hasSuffix("/attributions") {
                actionBody = Self.everythingReply
            } else if path.split(separator: "/").count == 3, path.hasPrefix("/api/segments/") {
                actionBody = Self.segmentReplies[String(path.split(separator: "/").last ?? "")]
            } else if path == "/api/hands" {
                actionBody = Self.handsReply
            } else if path.hasPrefix("/api/hands/segment/") {
                actionBody = Self.attributionsReply
            } else if path == "/api/source-settings/resolve" {
                actionBody = Self.settingsReply
            } else if path.hasPrefix("/api/segments/document/"), path.hasSuffix("/matches") {
                Self.matchesQuery = request.url?.query
                actionBody = Self.matchesReply
            } else if path.hasPrefix("/api/segments/"), path.hasSuffix("/versions") {
                actionBody = Self.versionsReply
            } else if path.hasPrefix("/api/segments/"), path.hasSuffix("/readings") {
                actionBody = Self.readingsReply
            } else if path.hasPrefix("/api/editorial/segment/") {
                actionBody = Self.editorialReply
            } else if path == "/api/signs" {
                actionBody = Self.signsReply
            } else if path.hasPrefix("/api/signs/"), path.hasSuffix("/instances") {
                actionBody = Self.instancesReply
            } else if path.hasPrefix("/api/letterforms/segment/") {
                actionBody = Self.letterformReply
            } else if path == "/api/letterforms/allographs" {
                actionBody = Self.allographsReply
            } else if path.hasPrefix("/api/links/of/") {
                actionBody = Self.linksReply
            } else if path == "/api/links/types" {
                actionBody = Self.linkTypesReply
            } else if path.hasPrefix("/api/segments/"), path.hasSuffix("/reference") {
                actionBody = Self.referenceReply
            } else if path == "/api/rights/effective" {
                actionBody = Self.rightsReply
            } else if path.hasPrefix("/api/segments/"), path.hasSuffix("/statements") {
                actionBody = Self.statementsReply
            } else if path.hasPrefix("/api/reading-orders/flows/onto/") {
                actionBody = Self.flowsOntoReply
            } else if path.hasPrefix("/api/reading-orders/document/") {
                actionBody = Self.ordersReply
            } else if path == "/api/formats" {
                actionBody = Self.formatsReply
            } else if path.hasPrefix("/api/documents/"), path.split(separator: "/").dropLast().last == "export" {
                Self.exportRequest = (path, request.url?.query)
                actionBody = Self.exportReply
            } else if path == "/api/locations/resolve" {
                Self.resolveRequests.append(Self.bodyOf(request))
                actionBody = Self.resolveReply
            } else if path.hasPrefix("/api/reading-orders/"), path.hasSuffix("/neighbours") {
                Self.neighboursQuery = request.url?.query
                actionBody = Self.neighboursReply
            } else if path.hasPrefix("/api/reading-orders/"), path.hasSuffix("/entries") {
                let query = request.url?.query ?? ""
                actionBody = !Self.childrenOf.isEmpty && query == "parent_entry_id=\(Self.childrenOf)"
                    ? Self.childEntriesReply : Self.topEntriesReply
            } else if path.hasPrefix("/api/reading-orders/"), path.hasSuffix("/place") {
                Self.placed.append(Self.bodyOf(request))
                actionBody = Self.actionReply(auditId: "place-\(Self.placed.count)")
            } else if path.hasPrefix("/api/segments/passes/"), path.hasSuffix("/original") {
                actionBody = Self.originalReply
            } else if path == "/api/actions/invoke" {
                Self.invoked.append(Self.bodyOf(request))
                let auditId = "audit-\(Self.invoked.count)"
                actionBody = Data(
                    #"{"ok":true,"result":\#(Self.invokeResult),"audit_id":"\#(auditId)","changed_domains":["segment"]}"#.utf8
                )
            } else if path.hasPrefix("/api/actions/audit/"), path.hasSuffix("/undo") {
                let auditId = path.split(separator: "/").dropLast().last.map(String.init) ?? ""
                Self.undone.append(auditId)
                actionBody = Self.actionReply(auditId: "undo-of-\(auditId)")
            }
            guard let url = request.url,
                  let response = HTTPURLResponse(
                      url: url, statusCode: isAnnotation ? 422 : (path == "/api/actions/invoke" ? Self.invokeStatus : 200),
                      httpVersion: "HTTP/1.1",
                      headerFields: ["Content-Type": isPicture ? "image/png" : "application/json"]
                  ) else {
                client?.urlProtocol(self, didFailWithError: URLError(.badURL))
                return
            }
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: actionBody ?? (isAnnotation ? Data("{}".utf8) : Self.body))
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}

        /// Every recorded request and canned reply back to empty: the class's state is static, so one
        /// test's recordings must not be read by the next.
        static func reset() {
            body = Data()
            annotationRequests = []
            invoked = []
            undone = []
            invokeStatus = 200
            invokeUnreachable = false
            invokeResult = "{}"
            handsReply = Data()
            attributionsReply = Data()
            settingsReply = Data()
            readingsReply = Data()
            versionsReply = Data()
            matchesReply = Data()
            matchesQuery = nil
            originalReply = Data()
            editorialReply = Data()
            signsReply = Data()
            instancesReply = Data()
            letterformReply = Data()
            allographsReply = Data()
            linksReply = Data()
            linkTypesReply = Data()
            referenceReply = Data()
            rightsReply = Data()
            statementsReply = Data()
            ordersReply = Data()
            neighboursReply = Data()
            flowsOntoReply = Data()
            resolveReply = Data()
            formatsReply = Data()
            exportReply = Data()
            exportRequest = nil
            resolveRequests = []
            neighboursQuery = nil
            topEntriesReply = Data()
            childEntriesReply = Data()
            childrenOf = ""
            placed = []
            everythingReply = Data()
            segmentReplies = [:]
            pictureReply = Data()
        }

        /// URLSession hands a protocol its body as a stream, not as `httpBody`.
        private static func bodyOf(_ request: URLRequest) -> Data {
            if let body = request.httpBody { return body }
            guard let stream = request.httpBodyStream else { return Data() }
            stream.open()
            defer { stream.close() }
            var data = Data()
            var buffer = [UInt8](repeating: 0, count: 4096)
            // Read until the stream says it is done: `hasBytesAvailable` can be false before the first
            // bytes arrive, which read a whole body as empty.
            while true {
                let read = stream.read(&buffer, maxLength: buffer.count)
                guard read > 0 else { break }
                data.append(buffer, count: read)
            }
            return data
        }
    }

    private struct ExpectedBox: Decodable {
        let level: String
        let bbox: [Double]
    }

    /// The client `loadedStore` built, so a test's other services talk to the same recorded engine.
    private var storeClient: FicheroClient?

    override func setUp() async throws {
        try await super.setUp()
        RecordedEngine.reset()
    }

    override func tearDown() async throws {
        RecordedEngine.reset()
        storeClient = nil
        try await super.tearDown()
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
        storeClient = client
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

    /// Q6 end to end: a Highlight made on the selection -- two lines picked on the imported page --
    /// SENDS those lines' segment ids as `targets`, through the calls the Preview's Highlight makes
    /// (`MarkTargets.selectedSegments` -> `segmentIds(in:)` -> `AnnotationStore.addNote`).
    func testAHighlightOnTwoSelectedLinesSendsTheirSegmentIds() async throws {
        let store = try await loadedStore()
        let selected = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        let scope = try XCTUnwrap(SegmentDisplay.selectionScope(artifactId: selected.artifactId, passId: selected.passId))
        let boxes = selected.geometry.boxes
        let lines = boxes.indices.filter { boxes[$0].level == "line" }.prefix(2)
        XCTAssertEqual(lines.count, 2)
        let selection = RegionSelection()
        selection.selectAll(Array(lines), artifactId: scope, documentId: "doc-0001", in: boxes)

        let picked = MarkTargets.selectedSegments(selection: selection, documentId: "doc-0001", store: store)
        XCTAssertEqual(picked.count, 2)
        let annotations = AnnotationStore(annotationService: AnnotationService(ficheroClient: storeClient))
        RecordedEngine.annotationRequests = []
        for segment in picked {
            _ = await annotations.addNote(
                scope: .document("doc-0001"), text: "", bbox: segment.rect, kind: .highlight,
                targets: MarkTargets.segmentIds(in: segment.rect, selected: picked)
            )
        }

        let sent = try RecordedEngine.annotationRequests.map {
            try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any])
        }
        XCTAssertEqual(sent.count, 2)
        let targetIds = sent.map { request in
            ((request["targets"] as? [[String: Any]]) ?? []).compactMap { $0["segment_id"] as? String }
        }
        // Each strip names exactly the line it is drawn over, and together they are the two picked.
        XCTAssertEqual(targetIds.map(\.count), [1, 1])
        XCTAssertEqual(Set(targetIds.flatMap { $0 }), Set(picked.map(\.id)))
    }

    /// #5152 edit half, end to end: on the recorded imported Syriac page, two lines picked the way
    /// RegionInteractionLayer picks them are JOINED through the calls the Preview's Join makes
    /// (`SegmentEdit.join` -> `SegmentEditRunner.run` -> `ActionsService.invokeAction`): the engine
    /// is asked for `segment.merge` with exactly those two ids and the versions the list said, and
    /// ⌘Z asks it to undo THAT audit row.
    func testJoiningTwoImportedLinesSendsSegmentMergeAndUndoInvertsIt() async throws {
        let store = try await loadedStore()
        let selected = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        let scope = try XCTUnwrap(SegmentDisplay.selectionScope(artifactId: selected.artifactId, passId: selected.passId))
        let boxes = selected.geometry.boxes
        let lines = Array(boxes.indices.filter { boxes[$0].level == "line" }.prefix(2))
        let selection = RegionSelection()
        selection.selectAll(lines, artifactId: scope, documentId: "doc-0001", in: boxes)
        let ids = InspectorPath.selectedSegmentIds(selection: selection, documentId: "doc-0001", store: store)
        let picked = ids.compactMap { id in store.segments(documentId: "doc-0001").first { $0.id == id } }
        XCTAssertEqual(picked.count, 2)

        RecordedEngine.invoked = []
        RecordedEngine.undone = []
        let manager = UndoManager()
        manager.groupsByEvent = false
        let runner = SegmentEditRunner(actionsService: ActionsService(client: try XCTUnwrap(storeClient)), store: store)
        manager.beginUndoGrouping()
        let auditId = try await runner.run(
            try SegmentEdit.join(picked).get(), documentId: "doc-0001", actionName: "Join Segments", undoManager: manager
        )
        manager.endUndoGrouping()

        XCTAssertEqual(auditId, "audit-1")
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        XCTAssertEqual(sent["name"] as? String, "segment.merge")
        let params = try XCTUnwrap(sent["params"] as? [String: Any])
        XCTAssertEqual(params["segment_ids"] as? [String], ids)
        XCTAssertEqual(params["keep_id"] as? String, ids.first)
        XCTAssertEqual(params["expected_versions"] as? [String: Int], Dictionary(uniqueKeysWithValues: ids.map { ($0, 1) }))

        XCTAssertTrue(manager.canUndo)
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-1"], "⌘Z inverts the Join's own audit row")
    }

    /// #5149 end to end: the imported Syriac page's Making entry says its file, format and contents,
    /// and Show Original brings back the file's own bytes through `SegmentService.original` -- the
    /// engine's answer played with the REAL corpus file inside it.
    func testTheImportedPageSaysHowItWasMadeAndShowsItsOriginal() async throws {
        let store = try await loadedStore()
        let entries = InspectorMaking.entries(
            passes: store.passes(documentId: "doc-0001"), segments: store.segments(documentId: "doc-0001")
        )
        let entry = try XCTUnwrap(entries.first)
        XCTAssertEqual(entry.title, "Imported from escriptorium_syriac_onb-syr1-0001.page.xml")
        XCTAssertEqual(entry.detail, "PAGE XML · 12 lines, 4 regions")
        XCTAssertTrue(entry.hasOriginal)

        // The engine's corpus file, beside the app target's parent (`fichero/../fichero-server`).
        let corpus = try AppSource.sibling("../fichero-server/tests/unit/formats/fixtures/corpus")
            .appendingPathComponent("escriptorium_syriac_onb-syr1-0001.page.xml").standardizedFileURL
        let fileBytes = try Data(contentsOf: corpus)
        RecordedEngine.originalReply = try JSONSerialization.data(withJSONObject: [
            "pass_id": entry.passId, "file_name": "escriptorium_syriac_onb-syr1-0001.page.xml",
            "import_format": "pagexml", "media_type": "application/xml",
            "content_base64": fileBytes.base64EncodedString()
        ])
        let service = SegmentService(ficheroClient: try XCTUnwrap(storeClient))
        let fetched = try await service.original(passId: entry.passId)
        let original = try XCTUnwrap(fetched)
        XCTAssertEqual(original.bytes, fileBytes, "Show Original is the file byte for byte")
        XCTAssertEqual(original.text, String(data: fileBytes, encoding: .utf8), "shown as the file's own text")
    }

    /// #5153 end to end: on the imported Syriac page's first line -- the file's reading and a person's
    /// correction of it, the correction COUNTING because it corrects the other (#5175, the engine's
    /// recorded answer) -- the Text section reads both through `SegmentService.readings` and says WHY the
    /// correction counts; "Make This Count" on the file's reading sends `reading.choose` with its id, and
    /// ⌘Z undoes that choice by its own audit id.
    func testChoosingTheFilesReadingOverACorrectionSendsReadingChooseAndUndoes() async throws {
        _ = try await loadedStore()
        RecordedEngine.readingsReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-readings.json")
        )
        let service = SegmentService(ficheroClient: try XCTUnwrap(storeClient))
        let fetched = try await service.readings(segmentId: "seg-0003")
        let text = try XCTUnwrap(fetched)
        XCTAssertEqual(text.readings.map(\.id), ["rep-0001", "rep-0002"])
        XCTAssertEqual(text.counting["transcription"]?.readingId, "rep-0002")
        XCTAssertEqual(text.counting["transcription"]?.why, .correction, "the correction counts, and says why")
        XCTAssertEqual(text.readings[1].correctsId, "rep-0001", "the correction says what it corrects")

        let params = try XCTUnwrap(ReadingChoice.choose(text.readings[0], of: "seg-0003", in: text))
        RecordedEngine.invoked = []
        RecordedEngine.undone = []
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        let auditId = try await ReadingChoice.run(
            params, actionsService: ActionsService(client: try XCTUnwrap(storeClient)), undoManager: manager,
            afterChange: {}
        )
        manager.endUndoGrouping()

        XCTAssertEqual(auditId, "audit-1")
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        XCTAssertEqual(sent["name"] as? String, "reading.choose")
        XCTAssertEqual(sent["params"] as? [String: String],
                       ["segment_id": "seg-0003", "kind": "transcription", "representation_id": "rep-0001"])
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-1"])
    }

    /// #5155 end to end: one selection across the surfaces. On the recorded imported Syriac page, a
    /// line named by the Reader's caret (the page's `lineFocused` message) or picked in the Order list
    /// becomes the Source view's selection -- its box lights -- and the Inspector's own resolution
    /// reads back exactly that line; an id not on the shown pass selects nothing.
    func testALineNamedByTheReaderIsTheSourceViewsSelectionAndTheInspectors() async throws {
        let store = try await loadedStore()
        let shown = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        let line = try XCTUnwrap(store.segments(documentId: "doc-0001").first { $0.kind == "line" })
        let focus = try XCTUnwrap(ReaderLineSelection.focus(from: ["pageId": "doc-0001", "segmentId": line.id]))

        let selection = RegionSelection()
        let selected = InspectorPath.select(
            segmentIds: [focus.segmentId], into: selection, documentId: focus.pageId, store: store
        )
        XCTAssertEqual(selected, [line.id])
        XCTAssertEqual(selection.resolvedIndices(in: shown.geometry.boxes), [try XCTUnwrap(line.boxIndex)], "its box lights")
        XCTAssertEqual(
            InspectorPath.selectedSegmentIds(selection: selection, documentId: "doc-0001", store: store), [line.id],
            "the Inspector inspects the same line"
        )

        let nothing = RegionSelection()
        XCTAssertTrue(InspectorPath.select(segmentIds: ["not-on-this-page"], into: nothing, documentId: "doc-0001", store: store).isEmpty)
        XCTAssertTrue(nothing.isEmpty)
    }

    /// #5156 end to end: the imported page's Making entry says its pass is the working one and why
    /// (the engine's recorded answer), and "Make Working" sends `pass.choose_working` through the
    /// calls the Making section makes (`WorkingPassChoice.run`), re-reading the page; ⌘Z undoes that
    /// audit row. (The recorded page has one pass, so the verb is driven for it directly: the UI
    /// offers it only on a pass that is not working.)
    func testMakeWorkingSendsPassChooseWorkingAndUndoes() async throws {
        let store = try await loadedStore()
        let entry = try XCTUnwrap(InspectorMaking.entries(
            passes: store.passes(documentId: "doc-0001"), segments: store.segments(documentId: "doc-0001")
        ).first)
        XCTAssertTrue(entry.working)
        XCTAssertEqual(entry.workingNote, "Working · by the project's rule")

        RecordedEngine.invoked = []
        RecordedEngine.undone = []
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        let auditId = try await WorkingPassChoice.run(
            documentId: "doc-0001", passId: entry.passId,
            actionsService: ActionsService(client: try XCTUnwrap(storeClient)), store: store, undoManager: manager
        )
        manager.endUndoGrouping()
        XCTAssertEqual(auditId, "audit-1")
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        XCTAssertEqual(sent["name"] as? String, "pass.choose_working")
        XCTAssertEqual(sent["params"] as? [String: String], ["document_id": "doc-0001", "pass_id": entry.passId])
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-1"])
    }

    /// #5157 end to end: on the recorded imported Syriac page, two lines picked the way the canvas
    /// picks them are set right-to-left through the Segment menu's call (`SegmentEdit.set` ->
    /// `SegmentEditRunner.run`): the engine is asked for ONE segment.update_many carrying both lines,
    /// each with the version the list said; ⌘Z undoes that one audit row.
    func testTheSegmentMenuSetsDirectionOnTwoImportedLinesInOneUndoableCall() async throws {
        let store = try await loadedStore()
        let shown = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        let scope = try XCTUnwrap(SegmentDisplay.selectionScope(artifactId: shown.artifactId, passId: shown.passId))
        let lines = Array(shown.geometry.boxes.indices.filter { shown.geometry.boxes[$0].level == "line" }.prefix(2))
        let selection = RegionSelection()
        selection.selectAll(lines, artifactId: scope, documentId: "doc-0001", in: shown.geometry.boxes)
        let ids = InspectorPath.selectedSegmentIds(selection: selection, documentId: "doc-0001", store: store)
        let picked = ids.compactMap { id in store.segments(documentId: "doc-0001").first { $0.id == id } }

        RecordedEngine.invoked = []
        RecordedEngine.undone = []
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        let runner = SegmentEditRunner(actionsService: ActionsService(client: try XCTUnwrap(storeClient)), store: store)
        _ = try await runner.run(
            try SegmentEdit.set(.direction("rtl"), on: picked).get(), documentId: "doc-0001",
            actionName: "Set Segment", undoManager: manager
        )
        manager.endUndoGrouping()

        XCTAssertEqual(RecordedEngine.invoked.count, 1, "one call for the whole selection")
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        XCTAssertEqual(sent["name"] as? String, "segment.update_many")
        let updates = try XCTUnwrap((sent["params"] as? [String: Any])?["updates"] as? [[String: Any]])
        XCTAssertEqual(updates.compactMap { $0["segment_id"] as? String }, ids)
        XCTAssertTrue(updates.allSatisfy { $0["direction"] as? String == "rtl" && $0["expected_version"] as? Int == 1 })
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-1"])
    }

    /// #5171 end to end: a direction set from the Segment menu or the Inspector (both `SegmentEditRunner.run`)
    /// reaches the Reader, which re-reads the page through the SAME observer it holds
    /// (`SegmentChangeObserver`, `DocumentKGWebPaneCoordinatorMacOS.segmentChanges`). The set, its ⌘Z and
    /// its ⇧⌘Z each re-read the page ONCE -- not zero (the change would show only on the next open), not
    /// twice, and never on a timer. Breaks if the runner stops posting, or posts on only one of the three.
    func testADirectionSetItsUndoAndItsRedoEachReloadTheReadersPageOnce() async throws {
        let store = try await loadedStore()
        let picked = Array(store.segments(documentId: "doc-0001").filter { $0.kind == "line" }.prefix(1))
        final class Reloads { var pages: [String] = [] }
        let reloaded = Reloads()
        let observer = SegmentChangeObserver { pageId in reloaded.pages.append(pageId) }
        let settle = { (count: Int) in
            for _ in 0..<200 where reloaded.pages.count < count { try await Task.sleep(nanoseconds: 10_000_000) }
            try await Task.sleep(nanoseconds: 50_000_000)  // a second, unwanted reload would land here
        }

        RecordedEngine.undone = []
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        _ = try await SegmentEditRunner(actionsService: ActionsService(client: try XCTUnwrap(storeClient)), store: store).run(
            try SegmentEdit.set(.direction("ltr"), on: picked).get(), documentId: "doc-0001",
            actionName: "Set Segment", undoManager: manager
        )
        manager.endUndoGrouping()
        try await settle(1)
        XCTAssertEqual(reloaded.pages, ["doc-0001"], "the set re-reads the page once")

        manager.undo()
        try await settle(2)
        XCTAssertEqual(RecordedEngine.undone, ["audit-1"])
        XCTAssertEqual(reloaded.pages, ["doc-0001", "doc-0001"], "its ⌘Z re-reads it once more")

        manager.redo()
        try await settle(3)
        XCTAssertEqual(RecordedEngine.undone, ["audit-1", "undo-of-audit-1"], "⇧⌘Z inverts the undo's own row")
        XCTAssertEqual(reloaded.pages, ["doc-0001", "doc-0001", "doc-0001"], "its ⇧⌘Z once more")
        withExtendedLifetime(observer) {}
    }

    /// #5158 end to end: the imported Syriac page's first line, through `SegmentService.resolvedSettings`
    /// over the engine's recorded answer. What the section shows is exactly what the engine says: the
    /// script DETECTED from the line's own letters (Syrc), the direction from that script (right to left),
    /// and a language nothing states -- "Not determined", never an English fallback (#5176).
    func testTheLanguageSectionShowsTheEnginesAnswerAndWhereEachFactCameFrom() async throws {
        _ = try await loadedStore()
        RecordedEngine.settingsReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-settings.json")
        )
        let settings = try await SegmentService(ficheroClient: try XCTUnwrap(storeClient))
            .resolvedSettings(segmentId: "seg-0003")
        let rows = Dictionary(uniqueKeysWithValues: InspectorLanguage.rows(settings).map { ($0.key, $0) })
        XCTAssertEqual(rows["script"]?.value, "Syrc")
        XCTAssertEqual(rows["script"]?.origin, "detected")
        XCTAssertEqual(rows["direction"]?.value, "Right to Left")
        XCTAssertEqual(rows["direction"]?.origin, "from the script")
        XCTAssertEqual(rows["language"]?.value, "Not determined")
        XCTAssertEqual(rows["language"]?.origin, "not determined")
        XCTAssertEqual(rows["encoding"]?.value, "Not determined")
    }

    /// #5161 end to end: the imported Syriac page's first line, attributed to hand B by a person (the
    /// engine's recorded answers for GET /api/hands and /api/hands/segment/{id}), read through
    /// `HandService`: the ink and the record on separate lines; "Withdraw" sends hand.unattribute for
    /// that attribution through `AuditedAction.run`, and ⌘Z undoes it.
    func testTheHandsSectionShowsTheAttributionAndWithdrawsItUndoably() async throws {
        _ = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-hands.json")
        )) as? [String: Any])
        RecordedEngine.handsReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["hands"]))
        RecordedEngine.attributionsReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["attributions"]))
        let service = HandService(client: try XCTUnwrap(storeClient))
        let rows = InspectorHands.rows(
            try await service.attributions(segmentId: "seg-0003"), hands: try await service.hands()
        )
        XCTAssertEqual(rows.map(\.ink), ["hand B (Estrangela)"])
        XCTAssertEqual(rows.map(\.record), ["judged by owner · sure 80%"])

        RecordedEngine.invoked = []
        RecordedEngine.undone = []
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        let result = try await AuditedAction.run(
            "hand.unattribute", params: HandUnattributeRequest(attributionId: rows[0].attributionId),
            actionName: "Withdraw Attribution", actionsService: ActionsService(client: try XCTUnwrap(storeClient)),
            undoManager: manager
        )
        manager.endUndoGrouping()
        XCTAssertEqual(result.auditId, "audit-1")
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        XCTAssertEqual(sent["name"] as? String, "hand.unattribute")
        XCTAssertEqual(sent["params"] as? [String: String], ["attribution_id": "attr-0001"])
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-1"])
    }

    /// #5154 end to end, the app's half, in the shape the lead ruled: on the recorded imported Syriac
    /// page, the page's `lineSplit` {offset} for the first line becomes ONE `segment.split {at_offset,
    /// expected_version}` -- no geometry, the engine cuts -- and `lineJoin` {intoSegmentId} for its
    /// neighbour ONE `segment.merge` keeping the line before; `readingEdit` {basedOn} becomes
    /// `representation.create` correcting it. All through the calls the Reader's coordinator makes
    /// (`ReaderTextEdit` -> `AuditedAction` / `SegmentEditRunner`). Engine half:
    /// test_reader_typing_requests.py.
    func testTheReadersEditSplitAndJoinMessagesBecomeTheirActions() async throws {
        let store = try await loadedStore()
        let lines = store.segments(documentId: "doc-0001").filter { $0.kind == "line" }
            .sorted { ($0.boxIndex ?? 0) < ($1.boxIndex ?? 0) }
        let first = try XCTUnwrap(lines.first)
        let second = try XCTUnwrap(lines.dropFirst().first)
        let actions = ActionsService(client: try XCTUnwrap(storeClient))

        let edit = try XCTUnwrap(ReaderTextEdit.message(from: [
            "kind": "readingEdit", "pageId": "doc-0001", "segmentId": first.id, "text": "ܐܒܓ", "previous": "ܐܒ",
            "basedOn": "rep-0001"
        ]))
        try await AuditedAction.run(
            "representation.create", params: try XCTUnwrap(ReaderTextEdit.newReading(for: edit)), actionName: "Typing",
            actionsService: actions, undoManager: nil
        )
        let split = try XCTUnwrap(ReaderTextEdit.message(from: [
            "kind": "lineSplit", "pageId": "doc-0001", "segmentId": first.id, "offset": 3
        ]))
        try await AuditedAction.run(
            "segment.split", params: try ReaderTextEdit.split(split, of: first, shownText: nil).get(),
            actionName: "Split Line", actionsService: actions, undoManager: nil
        )
        let join = try XCTUnwrap(ReaderTextEdit.message(from: [
            "kind": "lineJoin", "pageId": "doc-0001", "segmentId": second.id, "intoSegmentId": first.id
        ]))
        try await SegmentEditRunner(actionsService: actions, store: store)
            .run(try ReaderTextEdit.join(join, segments: lines).get(), documentId: "doc-0001", actionName: "Join Lines", undoManager: nil)

        let sent = try RecordedEngine.invoked.map { try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
        XCTAssertEqual(sent.compactMap { $0["name"] as? String }, ["representation.create", "segment.split", "segment.merge"])
        let created = try XCTUnwrap(sent[0]["params"] as? [String: Any])
        XCTAssertEqual(created["corrects_representation_id"] as? String, "rep-0001")
        XCTAssertEqual(created["content"] as? String, "ܐܒܓ")
        let splitParams = try XCTUnwrap(sent[1]["params"] as? [String: Any])
        XCTAssertEqual(splitParams["segment_id"] as? String, first.id)
        XCTAssertEqual(splitParams["expected_version"] as? Int, 1)
        XCTAssertEqual(splitParams["at_offset"] as? Int, 3, "Syriac letters are one UTF-16 unit each")
        XCTAssertNil(splitParams["parts"], "no geometry from the app: the engine cuts")
        let mergeParams = try XCTUnwrap(sent[2]["params"] as? [String: Any])
        XCTAssertEqual(mergeParams["segment_ids"] as? [String], [first.id, second.id])
        XCTAssertEqual(mergeParams["keep_id"] as? String, first.id)
    }

    /// `source.sure.editorial-facts` / `brackets-are-drawn` end to end: the imported Syriac page's first
    /// line with a person's facts on it (its first three letters unclear, faded; two letters lost after
    /// the fifth), read through `EditorialService` over the engine's recorded answer. The section shows
    /// the text as the editor prints it -- under-dots and "[.2]", drawn by the engine, not in the
    /// reading -- and each fact's words; Withdraw sends `editorial.withdraw` for that fact and ⌘Z undoes
    /// it; Mark Unclear sends `editorial.record` over the whole counting reading.
    func testTheCertaintyAndDamageSectionShowsTheFactsDrawnAndWithdrawsOneUndoably() async throws {
        _ = try await loadedStore()
        RecordedEngine.editorialReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-editorial.json")
        )
        let answer = try await EditorialService(client: try XCTUnwrap(storeClient)).facts(segmentId: "seg-0003")
        XCTAssertEqual(answer.facts.map(\.id), ["fact-0001", "fact-0002"])
        let drawn = try XCTUnwrap(answer.drawn)
        // Three under-dotted letters, two plain ones, then the lost stretch drawn at its place.
        XCTAssertTrue(drawn.hasPrefix("\u{0710}\u{0323}\u{0712}\u{0323}\u{072A}\u{0323}\u{0717}\u{0721}[.2] "), drawn)
        let rows = InspectorEditorial.rows(answer.facts)
        XCTAssertEqual(rows.map(\.detail), [
            "letters 1–3 · faded · by owner · sure 80%", "after letter 5 · 2 characters · a hole · by owner"
        ])

        let actions = ActionsService(client: try XCTUnwrap(storeClient))
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        try await AuditedAction.run(
            "editorial.withdraw", params: EditorialFactRequest(factId: rows[0].factId), actionName: "Withdraw Editorial Fact",
            actionsService: actions, undoManager: manager
        )
        manager.endUndoGrouping()
        let reading = InspectorText.Reading(
            id: "rep-0001", kind: "transcription", content: "ܐܒܪܗܡ", maker: "external_import",
            author: nil, guideline: nil, pairId: nil, pairRole: nil
        )
        try await AuditedAction.run(
            "editorial.record", params: try XCTUnwrap(InspectorEditorial.record(.unclear, segmentId: "seg-0003", reading: reading)),
            actionName: "Mark Unclear", actionsService: actions, undoManager: nil
        )

        let sent = try RecordedEngine.invoked.map { try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
        XCTAssertEqual(sent.compactMap { $0["name"] as? String }, ["editorial.withdraw", "editorial.record"])
        XCTAssertEqual(sent[0]["params"] as? [String: String], ["fact_id": "fact-0001"])
        let marked = try XCTUnwrap(sent[1]["params"] as? [String: Any])
        XCTAssertEqual(marked["representation_id"] as? String, "rep-0001")
        XCTAssertEqual(marked["char_start"] as? Int, 0)
        XCTAssertEqual(marked["char_end"] as? Int, 5)
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-1"], "⌘Z withdraws the withdrawal by its own audit row")
    }

    /// `source.sign.declared`, `list-authority`, `gather-instances` end to end on the real MUFI page
    /// (Clm 13027 fol. 38r): a sign declared from its first line that uses U+F1AC, read through
    /// `SignService` over the engine's recorded answers. The line's Signs row names the sign, its code
    /// point and list number, that it is used once here and 50 times on the page, and that it was
    /// declared from this line.
    func testTheSignsSectionNamesTheMUFISignTheLineUsesAndHowOften() async throws {
        _ = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("mufi_clm13027-38r.signs.json")
        )) as? [String: Any])
        RecordedEngine.signsReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["signs"]))
        RecordedEngine.instancesReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["instances"]))
        let readings = try XCTUnwrap(recorded["readings"] as? [String: Any])
        let line = try XCTUnwrap((readings["items"] as? [[String: Any]])?.first?["content"] as? String)

        let service = SignService(client: try XCTUnwrap(storeClient))
        let signs = try await service.signs()
        let total = try await service.totalUses(signId: "sign-0001")
        XCTAssertEqual(total, 50, "every use on the page, by one query")
        let rows = InspectorSigns.rows(
            signs: signs, segmentId: "seg-mufi-0001", reading: line, usedInProject: ["sign-0001": total]
        )
        XCTAssertEqual(rows.map(\.title), ["MUFI abbreviation sign"])
        XCTAssertEqual(rows.first?.detail, "U+F1AC · MUFI F1AC · 1 here · 50 in the project · declared from this segment")
        XCTAssertEqual(rows.first?.glyph, "\u{F1AC}")
        XCTAssertEqual(InspectorSigns.rows(signs: signs, segmentId: "seg-other", reading: "no sign").count, 0)
    }

    /// `source.letterform.chain`, `features` end to end: one letter's box on the imported Syriac page,
    /// described as the Estrangela alaph of hand B with a wedged stem and a curved foot, read through
    /// `SignService` and `HandService` over the engine's recorded answers -- the chain in names, never
    /// ids.
    func testTheSignsSectionReadsACharactersLetterformInWords() async throws {
        _ = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-mark-letterform.json")
        )) as? [String: Any])
        RecordedEngine.letterformReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["description"]))
        RecordedEngine.allographsReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["allographs"]))
        RecordedEngine.handsReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["hands"]))
        let client = try XCTUnwrap(storeClient)

        let forms = try await SignService(client: client).letterforms(segmentId: "seg-mark")
        let allographs = try await SignService(client: client).allographNames()
        let hands = try await HandService(client: client).hands()
        let lines = InspectorSigns.lines(
            forms, allographs: allographs,
            hands: Dictionary(uniqueKeysWithValues: hands.map { ($0.id, $0.label) })
        )
        XCTAssertEqual(lines.map(\.chain), ["\u{0710} › Estrangela alaph › hand B"])
        XCTAssertEqual(lines.map(\.detail), ["stem wedged · foot curved · by owner"])
    }

    /// `source.link.typed`, `both-ways`, `source.segment.citable` end to end (5.7, #5164): on the
    /// imported Syriac page, its second line CONTINUES its first (the engine's recorded answers). Read
    /// through `LinkService` from the FIRST line, the section says "Is continued by Line · <the second
    /// line's words>", sure 90%, with its note; Link on the two lines picked sends typed_link.create
    /// first to second; Withdraw sends typed_link.delete and ⌘Z undoes it; Copy Reference reads the
    /// line's `fichero:segment/…`.
    func testTheLinksSectionReadsALinkFromThisEndLinksTwoLinesAndCopiesTheReference() async throws {
        let store = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-lines-links.json")
        )) as? [String: Any])
        RecordedEngine.linksReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["of_first"]))
        RecordedEngine.linkTypesReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["types"]))
        RecordedEngine.referenceReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["reference"]))
        let service = LinkService(client: try XCTUnwrap(storeClient))

        let links = try await service.links(of: "seg-0003")
        let rows = InspectorLinks.rows(links, segments: store.segments(documentId: "doc-0001"))
        let second = try XCTUnwrap(store.segments(documentId: "doc-0001").first { $0.id == "seg-0004" })
        XCTAssertEqual(rows.map(\.sentence), ["Is continued by"])
        XCTAssertEqual(rows.first?.other, "Line · " + String(try XCTUnwrap(second.text).prefix(40)) + "…")
        XCTAssertEqual(rows.first?.detail, "sure 90% · the sentence runs on")
        let types = try await service.types()
        XCTAssertTrue(types.map(\.key).starts(with: ["answers"]), "the library's types, as the menu offers them")
        let reference = try await service.reference(segmentId: "seg-0003")
        XCTAssertEqual(reference, "fichero:segment/library-0001/doc-0001/seg-0003")

        let actions = ActionsService(client: try XCTUnwrap(storeClient))
        let pair = try XCTUnwrap(InspectorLinks.pair(["seg-0004", "seg-0003"]))
        try await AuditedAction.run(
            "typed_link.create", params: TypedLinkCreateRequest(fromId: pair.from, toId: pair.to, linkType: "continues"),
            actionName: "Link Segments", actionsService: actions, undoManager: nil
        )
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        try await AuditedAction.run(
            "typed_link.delete", params: TypedLinkIdRequest(linkId: try XCTUnwrap(rows.first).linkId),
            actionName: "Withdraw Link", actionsService: actions, undoManager: manager
        )
        manager.endUndoGrouping()
        let sent = try RecordedEngine.invoked.map { try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
        XCTAssertEqual(sent.compactMap { $0["name"] as? String }, ["typed_link.create", "typed_link.delete"])
        XCTAssertEqual(sent[0]["params"] as? [String: String],
                       ["from_id": "seg-0004", "to_id": "seg-0003", "link_type": "continues"])
        XCTAssertEqual(sent[1]["params"] as? [String: String], ["link_id": "link-0001"])
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-2"], "⌘Z restores the withdrawn link by its own audit row")
    }

    /// `source.rights.record`, `tighten-only` end to end (5.8): the imported Syriac page's first line,
    /// with a label on the library, local models only for the page, and the line restricted to one
    /// reader (the engine's recorded answer). Read through `RightsService`, the section says what
    /// applies and places each record; Set ▸ No Models sends rights.set on the line; Withdraw sends
    /// rights.withdraw for the line's own record, and ⌘Z undoes it.
    func testTheRightsSectionSaysWhatAppliesAndWhereEachRecordSits() async throws {
        _ = try await loadedStore()
        RecordedEngine.rightsReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-rights.json")
        )
        let answer = try await RightsService(client: try XCTUnwrap(storeClient))
            .effective(targetKind: "segment", targetId: "seg-0003")
        XCTAssertEqual(InspectorRights.effect(answer).map(\.value), ["Only owner", "Local models only", "TK Attribution"])
        let rows = InspectorRights.rows(answer.records, targetKind: "segment", targetId: "seg-0003", pageId: "doc-0001")
        XCTAssertEqual(rows.map(\.place), ["On the library", "On this page", "On this segment"])
        XCTAssertEqual(rows.map(\.detail), [
            "labels: TK Attribution · held by Österreichische Nationalbibliothek · by owner",
            "local models only · agreement 2026-07 · by owner",
            "restricted to owner · by owner"
        ])

        let actions = ActionsService(client: try XCTUnwrap(storeClient))
        try await AuditedAction.run(
            "rights.set", params: RightsSetRequest(targetKind: "segment", targetId: "seg-0003", modelUse: "none"),
            actionName: "Set Model Rule", actionsService: actions, undoManager: nil
        )
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        try await AuditedAction.run(
            "rights.withdraw", params: RightsRecordIdRequest(recordId: rows[2].recordId),
            actionName: "Withdraw Rights Record", actionsService: actions, undoManager: manager
        )
        manager.endUndoGrouping()
        let sent = try RecordedEngine.invoked.map { try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
        XCTAssertEqual(sent.compactMap { $0["name"] as? String }, ["rights.set", "rights.withdraw"])
        XCTAssertEqual(sent[0]["params"] as? [String: String],
                       ["target_kind": "segment", "target_id": "seg-0003", "model_use": "none"])
        XCTAssertEqual(sent[1]["params"] as? [String: String], ["record_id": "rights-0003"])
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-2"])
    }

    /// `source.statement.on-segment`, `both-ways` end to end (5.7, statements): the imported Syriac
    /// page's first line, with a claim anchored to it and an entity mentioned on it (the engine's
    /// recorded answer). Read through `StatementService`, the section lists the claim -- saying it is
    /// anchored here, with its excerpt -- then the mention; opening each focuses THAT claim or entity in
    /// the one focus the knowledge views follow.
    func testWhatIsSaidAboutALineListsItsClaimAndMentionAndOpensEach() async throws {
        _ = try await loadedStore()
        RecordedEngine.statementsReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-statements.json")
        )
        let answer = try await StatementService(client: try XCTUnwrap(storeClient)).statements(segmentId: "seg-0003")
        let rows = InspectorStatements.rows(answer)
        XCTAssertEqual(rows.map(\.title), ["Abraham begat Isaac", "Abraham"])
        XCTAssertEqual(rows.map(\.isClaim), [true, false])
        XCTAssertEqual(rows.first?.detail, "unreviewed · confidence 50% · anchored here · “ܐܒܪܗܡ ܐܘܠܕ”")

        let focus = KGFocusState()
        focus.focusClaim(claimId: rows[0].targetId, entityId: nil, sourceDocumentId: "doc-0001")
        XCTAssertEqual(focus.focusedClaimId, "claim-0001")
        focus.focusEntity(entityId: rows[1].targetId, sourceDocumentId: "doc-0001")
        XCTAssertEqual(focus.focusedEntityId, "entity-0001")
        XCTAssertNil(focus.focusedClaimId, "opening an entity is not opening a claim")
    }

    /// `source.segments-pane.exists`, `reorders`, `selection-shared` end to end (#4942): the imported
    /// Syriac page in the Segments pane, over the engine's recorded reading order. Through the Order
    /// list's own store (`ReadingOrderStore` over `ReadingOrderService`, the one implementation) the
    /// pane lists the page's four regions, opens the first to its line with a path back up, moves a
    /// region down with ONE place call whose ⌘Z undoes it by its own audit row, and a row picked is
    /// the Source view's selection (`InspectorPath.select`, the call the list makes on a pick).
    func testTheSegmentsPaneListsOpensReordersAndSelectsTheImportedPagesSegments() async throws {
        let segmentStore = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.reading-order.json")
        )) as? [String: Any])
        RecordedEngine.ordersReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["orders"]))
        RecordedEngine.topEntriesReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["top"]))
        RecordedEngine.childEntriesReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["children"]))
        RecordedEngine.childrenOf = try XCTUnwrap(recorded["region_entry"] as? String)
        let segments = segmentStore.segments(documentId: "doc-0001")

        let orders = ReadingOrderStore(transport: ReadingOrderService(ficheroClient: try XCTUnwrap(storeClient)))
        try await orders.load(documentId: "doc-0001")
        let top = orders.shown.map(\.segmentId)
        XCTAssertEqual(top.count, 4, "the page's four regions, in its order")
        XCTAssertEqual(top.map { id in segments.first { $0.id == id }?.kind }, Array(repeating: "region", count: 4))
        let region = try XCTUnwrap(top.first)
        XCTAssertTrue(SegmentsPane.hasChildren(region, in: segments), "a region opens to its lines")

        await orders.show(childrenOf: region)
        let lines = orders.shown.map(\.segmentId)
        XCTAssertEqual(lines.count, 1)
        let line = try XCTUnwrap(segments.first { $0.id == lines.first })
        XCTAssertEqual(line.kind, "line")
        XCTAssertEqual(SegmentsPane.rowLabel(line, at: 0), "Line · " + (line.text ?? "").trimmingCharacters(in: .whitespaces))
        XCTAssertEqual(SegmentsPane.path(pageTitle: "page", to: region, in: segments).map(\.title), ["page", "Region"])

        await orders.show(childrenOf: nil)
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        let auditId = await orders.move(region, step: .downward)
        orders.registerUndo(auditId: auditId, undoManager: manager, actionsService: ActionsService(client: try XCTUnwrap(storeClient)))
        manager.endUndoGrouping()
        XCTAssertEqual(auditId, "place-1")
        let placed = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.placed.first)) as? [String: Any])
        XCTAssertEqual(placed["segment_id"] as? String, region)
        XCTAssertEqual(placed["after_entry_id"] as? String, "entry-0002", "one place down: after the second region")
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["place-1"])

        let selection = RegionSelection()
        XCTAssertEqual(InspectorPath.select(segmentIds: [line.id], into: selection, documentId: "doc-0001", store: segmentStore), [line.id])
        XCTAssertEqual(InspectorPath.selectedSegmentIds(selection: selection, documentId: "doc-0001", store: segmentStore), [line.id])
    }

    /// `source.segments-pane.gathers` end to end, a hand (#4942): the imported Syriac page's first two
    /// lines attributed to hand B (the engine's recorded answer), gathered through the pane's own load
    /// (`SegmentsGatheredList.load` -> `HandService.everything` -> each segment read). Each row is the
    /// line's words with who judged and how sure, and opens the page it is on; nothing is withheld.
    func testEverythingInHandBIsGatheredWithEachLineAndItsJudgement() async throws {
        let store = try await loadedStore()
        RecordedEngine.everythingReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.everything-in-hand.json")
        )
        for segment in store.segments(documentId: "doc-0001") {
            let route = try XCTUnwrap(JSONSerialization.jsonObject(with: RecordedEngine.body) as? [String: Any])
            let raw = try XCTUnwrap((route["segments"] as? [[String: Any]])?.first { $0["id"] as? String == segment.id })
            RecordedEngine.segmentReplies[segment.id] = try JSONSerialization.data(withJSONObject: ["segment": raw])
        }
        let service = SegmentService(ficheroClient: try XCTUnwrap(storeClient))
        let answer = await SegmentsGatheredList.load(.hand(id: "hand-0001", label: "hand B"), segmentService: service)
        let lines = store.segments(documentId: "doc-0001")
        let first = try XCTUnwrap(lines.first { $0.id == "seg-0003" })
        XCTAssertEqual(answer.rows.count, 2)
        XCTAssertEqual(answer.rows.first?.title, SegmentsPane.rowLabel(first, at: 0))
        XCTAssertEqual(answer.rows.map(\.detail), ["judged by owner · sure 80%", "judged by owner · sure 60%"])
        XCTAssertEqual(answer.rows.map(\.documentId), ["doc-0001", "doc-0001"], "each opens the page it is on")
        XCTAssertEqual(answer.withheld, 0)
        XCTAssertNil(SegmentsGathered.withheldNote(answer.withheld))
    }

    /// `source.segments-pane.gathers` end to end, a sign (#4942): every instance of the MUFI sign
    /// declared on the real Clm 13027 page (the engine's recorded answer), gathered through the pane's
    /// own load -> `SignService.instances`: forty readings, each row how often the sign occurs in it,
    /// each opening its page.
    func testEveryInstanceOfTheMUFISignIsGathered() async throws {
        _ = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("mufi_clm13027-38r.signs.json")
        )) as? [String: Any])
        RecordedEngine.instancesReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["instances"]))
        let service = SegmentService(ficheroClient: try XCTUnwrap(storeClient))
        let answer = await SegmentsGatheredList.load(.sign(id: "sign-0001", name: "MUFI abbreviation sign"), segmentService: service)
        XCTAssertEqual(answer.rows.count, 40, "the page's forty readings that use U+F1AC")
        XCTAssertEqual(answer.rows.first?.detail, "once")
        XCTAssertTrue(answer.rows.allSatisfy { $0.documentId == "doc-mufi" }, "each opens the page it is on")
        XCTAssertEqual(answer.withheld, 0)
    }

    /// `source.segments-pane.views` end to end (#4942): a strip or grid cell's picture is the engine's
    /// own cut of the segment, read through `SegmentPictureService` as PNG. Recorded on the imported
    /// Syriac page's first line: the corpus has no scan, so the page image is a stand-in at the file's
    /// proportions with the file's lines inked, and the bytes are the engine's real cut of that line.
    func testAStripCellsPictureIsTheEnginesCutOfTheLine() async throws {
        _ = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-picture.json")
        )) as? [String: Any])
        let png = try XCTUnwrap(Data(base64Encoded: try XCTUnwrap(recorded["png_base64"] as? String)))
        RecordedEngine.pictureReply = png
        let fetched = try await SegmentPictureService(client: try XCTUnwrap(storeClient))
            .picture(segmentId: try XCTUnwrap(recorded["segment_id"] as? String), size: 120)
        let bytes = try XCTUnwrap(fetched, "a picture, not nil")
        XCTAssertEqual(bytes, png, "the engine's bytes, untouched")
        let image = try XCTUnwrap(PlatformImage(data: bytes))
        XCTAssertEqual(max(image.size.width, image.size.height), 120, accuracy: 1, "the size asked for")
        XCTAssertGreaterThan(image.size.width, image.size.height, "a line is wider than it is tall")
    }

    /// `source.textedit.a-run-of-keys-is-one-action` end to end, the app's half: a run of typing on the
    /// imported Syriac page's first line reaches the app as ONE `readingEdit` (the page coalesces the
    /// keys), and through the calls the Reader's coordinator makes it is ONE `representation.create`,
    /// ONE audit row and ONE undo step: ⌘Z once undoes the whole run, and there is nothing more.
    func testARunOfTypingIsOneReadingOneAuditOneUndo() async throws {
        let store = try await loadedStore()
        let line = try XCTUnwrap(store.segments(documentId: "doc-0001").first { $0.id == "seg-0003" })
        let typed = (line.text ?? "") + " ܘܐܝܣܚܩ"
        let edit = try XCTUnwrap(ReaderTextEdit.message(from: [
            "kind": "readingEdit", "pageId": "doc-0001", "segmentId": line.id, "text": typed,
            "previous": line.text ?? "", "basedOn": "rep-0001"
        ]))
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        RecordedEngine.invokeResult = #"{"id":"rep-0009","segment_id":"seg-0003"}"#
        let made = try await AuditedAction.run(
            "representation.create", params: try XCTUnwrap(ReaderTextEdit.newReading(for: edit)), actionName: "Typing",
            actionsService: ActionsService(client: try XCTUnwrap(storeClient)), undoManager: manager
        )
        manager.endUndoGrouping()
        XCTAssertEqual(RecordedEngine.invoked.count, 1, "one run of keys, one action")
        // The page is told the reading the run made, so a second run before the re-read is based on it.
        XCTAssertEqual(made.resultId, "rep-0009")
        let told = ReaderTextEdit.committedScript(
            pageId: "doc-0001", segmentId: line.id, reason: nil, representationId: made.resultId
        )
        let payload = try XCTUnwrap(
            JSONSerialization.jsonObject(
                with: Data(told.dropFirst("window.fichero?.lineCommitted?.(".count).dropLast(2).utf8)
            ) as? [String: Any]
        )
        XCTAssertEqual(payload["representationId"] as? String, "rep-0009")
        XCTAssertEqual(payload["ok"] as? Bool, true)
        XCTAssertEqual(manager.undoActionName, "Typing")
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-1"], "one ⌘Z undoes the whole run")
        XCTAssertFalse(manager.canUndo, "and there is no second step to undo")
    }

    /// `source.textedit.stale-keeps-your-words` end to end, the app's half, on the imported Syriac page's
    /// first line: typing against the file's reading (`rep-0001`) sends it as `expected_counting_id`;
    /// meanwhile a correction (`rep-0002`, the recorded readings) counts, so the engine refuses with 409.
    /// The page is told what counts now, with the typed words kept. Keep Mine is the same words sent
    /// against `rep-0002`, and it lands. Breaks if the token is not sent (a silent second candidate), or
    /// if the answer loses the words or names the wrong reading.
    func testATypedLineAgainstAReadingThatNoLongerCountsKeepsTheWordsAndNamesWhatCounts() async throws {
        _ = try await loadedStore()
        RecordedEngine.readingsReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-readings.json")
        )
        let typed = "ܡܢ ܕܝܠܝ"
        let edit = try XCTUnwrap(ReaderTextEdit.message(from: [
            "kind": "readingEdit", "pageId": "doc-0001", "segmentId": "seg-0003", "text": typed,
            "previous": "", "basedOn": "rep-0001"
        ]))
        let actions = ActionsService(client: try XCTUnwrap(storeClient))
        RecordedEngine.invoked = []
        RecordedEngine.invokeStatus = 409
        do {
            _ = try await actions.invokeAction(
                name: "representation.create", params: try XCTUnwrap(ReaderTextEdit.newReading(for: edit))
            )
            XCTFail("a stale write must be refused")
        } catch APIError.httpError(409, _) {}
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        let params = try XCTUnwrap(sent["params"] as? [String: Any])
        XCTAssertEqual(params["expected_counting_id"] as? String, "rep-0001", "the token is the reading typed over")

        let service = SegmentService(ficheroClient: try XCTUnwrap(storeClient))
        let answered = await ReaderTextEdit.staleAnswer(to: edit, readings: service)
        let script = try XCTUnwrap(answered)
        let json = try XCTUnwrap(
            script.dropFirst("window.fichero?.lineCommitted?.(".count).dropLast(2).data(using: .utf8)
        )
        let answer = try XCTUnwrap(JSONSerialization.jsonObject(with: json) as? [String: Any])
        XCTAssertEqual(answer["stale"] as? Bool, true)
        XCTAssertEqual(answer["ok"] as? Bool, false)
        XCTAssertEqual(answer["mine"] as? String, typed, "the typed words are kept")
        let theirs = try XCTUnwrap(answer["theirs"] as? [String: Any])
        XCTAssertEqual(theirs["representationId"] as? String, "rep-0002", "what counts now is named")
        XCTAssertEqual((theirs["text"] as? String)?.hasSuffix("(corrected)"), true, "and its words")

        // Keep Mine: the page sends the same words again, against what counts now.
        RecordedEngine.invokeStatus = 200
        let keep = try XCTUnwrap(ReaderTextEdit.message(from: [
            "kind": "readingEdit", "pageId": "doc-0001", "segmentId": "seg-0003", "text": typed,
            "previous": "", "basedOn": "rep-0002"
        ]))
        let kept = try await actions.invokeAction(
            name: "representation.create", params: try XCTUnwrap(ReaderTextEdit.newReading(for: keep))
        )
        XCTAssertTrue(kept.succeeded)
        let resent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.last)) as? [String: Any])
        XCTAssertEqual((resent["params"] as? [String: Any])?["expected_counting_id"] as? String, "rep-0002")
        XCTAssertEqual((resent["params"] as? [String: Any])?["content"] as? String, typed)
    }

    /// `source.segment.versioned-alone` end to end (#5163, the Inspector's Making section at segment
    /// level), on the imported Syriac page's first line after two recorded changes (moved, then its
    /// language set): the Section's calls read the two kept versions and the live row (version 3), say
    /// what each change did, and Restore sends `segment.restore_version` back to version 1 checked
    /// against version 3 -- the exact call the recorder proved the engine takes -- with ⌘Z by its own
    /// audit id. Breaks if a version is misread, the change it names is wrong, or Restore is checked
    /// against a version the app did not read.
    func testALinesHistoryShowsWhatEachChangeDidAndRestoreSendsTheCheckedCall() async throws {
        _ = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-history.json")
        )) as? [String: Any])
        RecordedEngine.versionsReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["versions"]))
        RecordedEngine.segmentReplies["seg-0003"] = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["live"]))
        let service = SegmentService(ficheroClient: try XCTUnwrap(storeClient))

        let versions = try await service.versions(segmentId: "seg-0003")
        let fetched = try await service.segment(id: "seg-0003")
        let live = try XCTUnwrap(fetched)
        XCTAssertEqual(versions.map(\.version), [1, 2])
        XCTAssertEqual(live.version, 3)
        let rows = SegmentHistory.rows(versions, live: SegmentHistory.state(of: live))
        XCTAssertEqual(rows.map(\.version.version), [2, 1], "newest first")
        XCTAssertEqual(rows.map(\.then), [["language unset → syc"], ["moved or reshaped"]])
        XCTAssertEqual(SegmentHistory.baselineDescription(live.baseline), "Curved baseline, 3 points")
        XCTAssertEqual(SegmentHistory.baselineDescription([[0.1, 0.5], [0.9, 0.5]]), "Straight baseline, 2 points")
        var readAtTwo = live
        readAtTwo.version = 2
        XCTAssertNil(SegmentHistory.restore(try XCTUnwrap(versions.last), of: readAtTwo),
                     "a version is restored only when it is older than the one read")

        let params = try XCTUnwrap(SegmentHistory.restore(XCTUnwrap(versions.first), of: live))
        RecordedEngine.invoked = []
        RecordedEngine.undone = []
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        try await AuditedAction.run(
            "segment.restore_version", params: params, actionName: "Restore Version",
            actionsService: ActionsService(client: try XCTUnwrap(storeClient)), undoManager: manager
        )
        manager.endUndoGrouping()
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        XCTAssertEqual(sent["name"] as? String, "segment.restore_version")
        let sentParams = try XCTUnwrap(sent["params"] as? [String: Any])
        XCTAssertEqual(sentParams["segment_id"] as? String, "seg-0003")
        XCTAssertEqual(sentParams["version"] as? Int, 1)
        XCTAssertEqual(sentParams["expected_version"] as? Int, 3, "checked against the version the app read")
        XCTAssertEqual(manager.undoActionName, "Restore Version")
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-1"], "⌘Z undoes the restore by its own audit id")
    }

    /// `source.segment.table-cells` end to end (#5168), on a real Transkribus table page (recorded
    /// reduced to the table and its 172 cells): through the store's own load, a cell's path head names
    /// the table and the cell by its place, counted from 1 as people count ("Rows 3–4, Column 1" for
    /// the file's row 2 spanning two), and the Segments pane's row labels say the same. Breaks if a
    /// cell's place is lost on the way, counted from 0, or its span dropped.
    func testATableCellIsNamedByItsRowAndColumnInThePathAndTheRows() async throws {
        let store = try await loadedStore()
        RecordedEngine.body = try Data(
            contentsOf: fixtures().appendingPathComponent("transkribus_abp_table_0019.route.json")
        )
        await store.load(documentId: "doc-0001", force: true)
        let segments = store.segments(documentId: "doc-0001")
        XCTAssertEqual(segments.filter { $0.cell != nil }.count, 172, "every cell's place arrived")
        let table = try XCTUnwrap(segments.first { $0.kind == "table" })

        let spanning = try XCTUnwrap(segments.first { $0.id == "seg-0006" })
        XCTAssertEqual(spanning.cell?.row, 2)
        XCTAssertEqual(spanning.cell?.rowSpan, 2)
        let path = try XCTUnwrap(InspectorPath.to(spanning.id, in: segments))
        XCTAssertEqual(path.crumbs.map(\.label), ["Table", "Cell, Rows 3–4, Column 1"])
        XCTAssertEqual(path.crumbs.first?.segmentId, table.id)

        let plain = try XCTUnwrap(segments.first { $0.id == "seg-0003" })
        XCTAssertEqual(SegmentsPane.rowLabel(plain, at: 0), "Cell, Row 13, Column 1", "no count after a place")
        let steps = SegmentsPane.path(pageTitle: "Page", to: spanning.id, in: segments)
        XCTAssertEqual(steps.map(\.title), ["Page", "Table", "Cell, Rows 3–4, Column 1"])
    }

    /// `source.segment.match-record` end to end (#5165, the Segments pane's "Proposed matches"), on the
    /// imported Syriac page with two recorded proposals: the set's own load asks for the page's
    /// PROPOSED matches, each row names the newer line and says what it was matched to, who proposed it
    /// and how sure; Accept and Reject send the audited verbs with the match's id -- the exact calls the
    /// recorder proved the engine takes -- each ⌘Z-able by its own audit id. Breaks if reviewed matches
    /// are asked for, a row names the wrong segment, or a verb carries the wrong match.
    func testAPagesProposedMatchesAreListedAndAcceptAndRejectSendTheirVerbs() async throws {
        let store = try await loadedStore()
        RecordedEngine.matchesReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.proposed-matches.json")
        )
        let service = SegmentService(ficheroClient: try XCTUnwrap(storeClient))
        let answer = await SegmentsGatheredList.load(.matches(documentId: "doc-0001"), segmentService: service)
        XCTAssertEqual(RecordedEngine.matchesQuery, "state=proposed", "only what waits for review")
        let segments = Dictionary(store.segments(documentId: "doc-0001").map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        XCTAssertEqual(answer.rows.map(\.matchId), ["match-0001", "match-0002"])
        XCTAssertEqual(answer.rows.map(\.segmentId), ["seg-0010", "seg-0009"], "a row opens the newer segment")
        XCTAssertEqual(answer.rows.first?.title, SegmentsPane.rowLabel(segments["seg-0010"], at: 0))
        XCTAssertEqual(
            answer.rows.first?.detail, "was " + SegmentsPane.rowLabel(segments["seg-0012"], at: 0) + " · proposed by owner"
        )
        XCTAssertEqual(answer.rows.last?.detail.hasSuffix(" · proposed by owner · sure 60% · same words, redrawn box"), true)

        let actions = ActionsService(client: try XCTUnwrap(storeClient))
        RecordedEngine.invoked = []
        RecordedEngine.undone = []
        let manager = UndoManager()
        manager.groupsByEvent = false
        for (verb, row) in [("segment.match_accept", answer.rows[0]), ("segment.match_reject", answer.rows[1])] {
            manager.beginUndoGrouping()
            try await AuditedAction.run(
                verb, params: SegmentMatchIdRequest(matchId: try XCTUnwrap(row.matchId)), actionName: verb,
                actionsService: actions, undoManager: manager
            )
            manager.endUndoGrouping()
        }
        let sent = try RecordedEngine.invoked.map { try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
        XCTAssertEqual(sent.compactMap { $0["name"] as? String }, ["segment.match_accept", "segment.match_reject"])
        XCTAssertEqual(sent.compactMap { ($0["params"] as? [String: Any])?["match_id"] as? String }, ["match-0001", "match-0002"])
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-2"], "⌘Z undoes the reject by its own audit id")
    }

    /// `source.order.named-multiple`, `next-previous`, `source.segment.flow` end to end (#5160, the Order
    /// list's picker), over the recorded Syriac page with a named order and a flow that continues onto a
    /// second imported page: the store lists all three orders and switches to the flow; New Flow sends
    /// the exact create the recorder proved (same pass, `seed_from_pass`) and finds what it made; Next
    /// from the flow's last line on this page asks the neighbours route and lands on the next page's
    /// line, whose page it opens. Breaks if an order is missing, the create differs from what the engine
    /// takes, or Next stays on the page when the flow leaves it.
    func testTheOrderPickerListsNamedOrdersAndAFlowWhoseNextOpensTheNextPage() async throws {
        let segments = try await loadedStore().segments(documentId: "doc-0001")
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.named-orders-and-flow.json")
        )) as? [String: Any])
        RecordedEngine.ordersReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["orders"]))
        RecordedEngine.topEntriesReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["flow_top"]))
        RecordedEngine.neighboursReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["neighbours"]))
        RecordedEngine.segmentReplies["seg-next-0001"] = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["across"]))
        let service = ReadingOrderService(ficheroClient: try XCTUnwrap(storeClient))
        let store = ReadingOrderStore(transport: service)

        try await store.load(documentId: "doc-0001")
        XCTAssertEqual(store.orders.map(ReadingOrderChoice.title), ["As Written", "Commentary order", "Into the next page (flow)"])
        XCTAssertEqual(store.orderId, "order-0001", "the file's own order first")
        try await store.choose("order-0003")
        XCTAssertEqual(store.orderId, "order-0003")
        XCTAssertEqual(store.entries.last?.segmentId, "seg-next-0001", "the flow ends on the next page")

        let asWritten = try XCTUnwrap(store.orders.first)
        let params = try XCTUnwrap(ReadingOrderChoice.create(.flow, name: " Into the next page ", documentId: "doc-0001", from: asWritten))
        XCTAssertEqual(params, ReadingOrderCreateRequest(
            documentId: "doc-0001", passId: "pass-0002", name: "Into the next page", kind: "flow", seedFromPass: true
        ))
        XCTAssertNil(ReadingOrderChoice.create(.named, name: "  ", documentId: "doc-0001", from: asWritten), "a name is needed")
        RecordedEngine.invoked = []
        try await AuditedAction.run(
            "reading_order.create", params: params, actionName: "New Flow",
            actionsService: ActionsService(client: try XCTUnwrap(storeClient)), undoManager: nil
        )
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        let sentParams = try XCTUnwrap(sent["params"] as? [String: Any])
        XCTAssertEqual(sentParams["pass_id"] as? String, "pass-0002")
        XCTAssertEqual(sentParams["kind"] as? String, "flow")
        XCTAssertEqual(sentParams["seed_from_pass"] as? Bool, true)
        XCTAssertEqual(
            ReadingOrderChoice.made(named: "Into the next page", before: Array(store.orders.prefix(2)), after: store.orders)?.id,
            "order-0003"
        )

        let neighbours = try await service.neighbours(orderId: "order-0003", segmentId: "seg-0014")
        XCTAssertEqual(RecordedEngine.neighboursQuery, "segment_id=seg-0014")
        XCTAssertEqual(neighbours, ReadingOrderChoice.Neighbours(previous: "seg-0018", next: "seg-next-0001"))
        let target = try XCTUnwrap(ReadingOrderChoice.target(neighbours, forward: true))
        XCTAssertFalse(segments.contains { $0.id == target }, "Next leaves this page")
        let fetched = try await SegmentService(ficheroClient: try XCTUnwrap(storeClient)).segment(id: target)
        XCTAssertEqual(fetched?.documentId, "doc-0002", "the page Next opens")
    }

    /// `source.segment.citable` end to end (#5164, the app's URL handler), with the engine's own
    /// reference to the imported Syriac page's first line: the URL parses, the WHOLE string is sent to
    /// the one resolver (so the engine checks its library and page parts), and the answer lands on the
    /// page and the line. After the line was merged into the next, the same reference lands on the line
    /// that absorbed it. Breaks if the handler sends only the bare id, or lands on a stale segment.
    func testASegmentReferenceURLResolvesToItsPageAndFollowsAMerge() async throws {
        _ = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.reference-resolved.json")
        )) as? [String: Any])
        let string = try XCTUnwrap(recorded["reference"] as? String)
        let reference = try XCTUnwrap(SegmentReference.parse(XCTUnwrap(URL(string: string))))
        XCTAssertEqual(reference.segmentId, "seg-0012")
        let locations = LocationService(ficheroClient: try XCTUnwrap(storeClient))

        RecordedEngine.resolveReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["direct"]))
        let landing = try await reference.resolve(with: locations)
        XCTAssertEqual(landing, ReadingOrderChoice.Landing(documentId: "doc-0001", segmentId: "seg-0012"))
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.resolveRequests.first)) as? [String: Any])
        XCTAssertEqual(sent["segmentId"] as? String, string, "the whole reference, not the bare id")

        RecordedEngine.resolveReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["after_merge"]))
        let followed = try await reference.resolve(with: locations)
        XCTAssertEqual(followed, ReadingOrderChoice.Landing(documentId: "doc-0001", segmentId: "seg-0010"),
                       "an old reference opens the line that absorbed it")
    }

    /// `source.format.export-choices` end to end (#5162, Inspector › Making's per-pass Export), on the
    /// imported Syriac page: the choices are built from what the engine WRITES (a text pass is offered
    /// the text formats, a georeferencing pass only the georeference ones); exporting the pass the
    /// person picked sends its id (`pass_id`) and the engine says it exported that pass; the file is
    /// named for its format by the engine (hOCR as `x.hocr`, the imported file's own `.page` dropped); and "as imported"
    /// is the original file byte for byte (its SHA-256 is the file's). Breaks if a written format is
    /// missing, the wrong pass is exported, or "as imported" is anything but the file.
    func testExportChoicesOfferWhatTheEngineWritesPerPassAndAsImportedIsTheFile() async throws {
        _ = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.export-choices.json")
        )) as? [String: Any])
        RecordedEngine.formatsReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["formats"]))
        RecordedEngine.exportReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["export"]))
        RecordedEngine.originalReply = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["original"]))
        let client = try XCTUnwrap(storeClient)

        let formats = try await DocumentService(ficheroClient: client).formats()
        XCTAssertEqual(PageExportChoice.offers(formats, georeferencing: false).map(\.title),
                       ["PAGE XML", "ALTO", "TEI", "hOCR", "YOLO"])
        XCTAssertEqual(PageExportChoice.offers(formats, georeferencing: true).map(\.title),
                       ["IIIF Georeference", "QGIS Points"])

        let hocr = try XCTUnwrap(formats.first { $0.name == "hocr" })
        let result = try await DocumentService(ficheroClient: client).exportPage(
            documentId: "doc-0001", format: hocr.name, passId: "pass-0002"
        )
        XCTAssertEqual(RecordedEngine.exportRequest?.path, "/api/documents/doc-0001/export/hocr")
        XCTAssertEqual(RecordedEngine.exportRequest?.query, "pass_id=pass-0002", "the pass the person picked")
        XCTAssertEqual(result.choices.passId, "pass-0002")
        XCTAssertEqual(result.filename, "escriptorium_syriac_onb-syr1-0001.hocr",
                       "the engine names the file for its format, and the app saves it under that name")

        let fetched = try await SegmentService(ficheroClient: client).original(passId: "pass-0002")
        let original = try XCTUnwrap(fetched)
        XCTAssertEqual(original.fileName, "escriptorium_syriac_onb-syr1-0001.page.xml")
        let digest = SHA256.hash(data: original.bytes).map { String(format: "%02x", $0) }.joined()
        XCTAssertEqual(digest, recorded["original_sha256"] as? String, "as imported: the file, byte for byte")
    }

    /// `source.segment.shape-kinds`, `curved-baseline`, `source.editor.reshape` end to end, on the
    /// imported Syriac page's recorded route (whose polygons and baselines the engine test pins to the
    /// PAGE file with lxml): the boxes the canvas draws carry each line's outline and baseline, so the
    /// overlay draws them as themselves; in Edit Segments a press on a side's midpoint adds a point
    /// (`SegmentShapes.handle`), and Reshape sends `segment.update` with the new polygon and the rect it
    /// bounds, checked against the version read -- the exact call the engine test proved lands -- with
    /// ⌘Z by its audit id; ⌥-click removes a baseline point, and never below two. Breaks if a shape is
    /// dropped on the way to the overlay, a point lands elsewhere than pressed, or the edit sent is not
    /// the one the engine takes.
    func testALinesOutlineAndBaselineAreDrawnAsThemselvesAndReshapeSendsTheCheckedUpdate() async throws {
        let store = try await loadedStore()
        let selected = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        let segments = store.segments(documentId: "doc-0001")
        let lines = segments.filter { $0.kind == "line" && $0.passId == selected.passId }
        XCTAssertEqual(lines.count, 12)
        for line in lines {
            let box = try XCTUnwrap(line.boxIndex.map { selected.geometry.boxes[$0] })
            XCTAssertEqual(box.shapes, [.polygon(try XCTUnwrap(line.anchor.polygon)), .baseline(try XCTUnwrap(line.baseline))],
                           "the line is drawn as its outline and its baseline, not its box")
        }

    }

    /// Reshape's outline half, on the same recorded line: a press on a side's midpoint adds a point,
    /// dragged, and the edit sent is the polygon with the rect it bounds, checked against the version
    /// read, ⌘Z by its audit id (the engine test proves this exact call lands and undoes).
    func testReshapingALinesOutlineSendsTheCheckedUpdateAndUndoes() async throws {
        let store = try await loadedStore()
        let selected = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        let line = try XCTUnwrap(store.segments(documentId: "doc-0001").first { $0.id == "seg-0003" })
        let box = selected.geometry.boxes[try XCTUnwrap(line.boxIndex)]
        let polygon = try XCTUnwrap(SegmentShapes.points(of: line, .polygon))
        let side = SegmentShapes.sideMidpoints(polygon, .polygon)[0]
        let reach = [0.004, 0.004]
        XCTAssertEqual(SegmentShapes.handle(at: side, in: box.shapes, tolerance: reach), .side(.polygon, 0))
        XCTAssertEqual(SegmentShapes.handle(at: polygon[2], in: box.shapes, tolerance: reach), .vertex(.polygon, 2))
        let added = SegmentShapes.moving(
            SegmentShapes.adding(polygon, after: 0, at: side, .polygon), index: 1, to: [side[0], side[1] - 0.01]
        )
        XCTAssertEqual(added.count, polygon.count + 1)
        XCTAssertEqual(added[1], [side[0], side[1] - 0.01], "the new point is where it was dragged")

        let call = try SegmentShapes.reshape(line, .polygon, to: added).get()
        RecordedEngine.invoked = []
        RecordedEngine.undone = []
        let manager = UndoManager()
        manager.groupsByEvent = false
        manager.beginUndoGrouping()
        try await SegmentEditRunner(actionsService: ActionsService(client: try XCTUnwrap(storeClient)), store: store).run(
            call, documentId: "doc-0001", actionName: "Reshape Segment", undoManager: manager
        )
        manager.endUndoGrouping()
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        XCTAssertEqual(sent["name"] as? String, "segment.update")
        let params = try XCTUnwrap(sent["params"] as? [String: Any])
        XCTAssertEqual(params["expected_version"] as? Int, line.version, "checked against the version read")
        let anchor = try XCTUnwrap(params["anchor"] as? [String: Any])
        assertClose(anchor["polygon"], added)
        assertClose(anchor["rect"], [SegmentShapes.bounds(added)], "the box is the outline's bounds")
        XCTAssertNil(params["baseline"], "an outline reshape leaves the baseline alone")
        XCTAssertEqual(manager.undoActionName, "Reshape Segment")
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-1"], "⌘Z undoes the reshape by its own audit id")
    }

    /// Reshape's baseline half and its limits: ⌥-click removes a baseline point and the edit is the
    /// baseline alone; a baseline keeps two points; an outline rewrite on a segment with extra shapes
    /// carries them, so none is dropped.
    func testReshapingABaselineSendsItAloneAndTheRefusalsHold() async throws {
        let store = try await loadedStore()
        let line = try XCTUnwrap(store.segments(documentId: "doc-0001").first { $0.id == "seg-0003" })
        let polygon = try XCTUnwrap(SegmentShapes.points(of: line, .polygon))
        let added = SegmentShapes.adding(polygon, after: 0, at: SegmentShapes.sideMidpoints(polygon, .polygon)[0], .polygon)
        let baseline = try XCTUnwrap(SegmentShapes.points(of: line, .baseline))
        let fewer = try XCTUnwrap(SegmentShapes.removing(baseline, index: 1, .baseline))
        guard case .baseline(let request) = try SegmentShapes.reshape(line, .baseline, to: fewer).get().params else {
            return XCTFail("a baseline reshape sends the baseline alone")
        }
        XCTAssertEqual(request, SegmentBaselineRequest(segmentId: line.id, expectedVersion: try XCTUnwrap(line.version), baseline: fewer))
        XCTAssertNil(SegmentShapes.removing(fewer, index: 0, .baseline), "a baseline keeps two points")
        var withShapes = line
        withShapes.anchor.shapes = [try makePointShape()]
        guard case .update(let rewrite) = try SegmentShapes.reshape(withShapes, .polygon, to: added).get().params else {
            return XCTFail("an outline reshape rewrites the anchor")
        }
        XCTAssertEqual(rewrite.anchor.shapes, [AnchorShapeParams(kind: "point", points: [[0.5, 0.5]], tStart: nil, tEnd: nil)],
                       "an anchor rewrite carries the extra shapes, never drops them")
        XCTAssertEqual(rewrite.anchor.polygon, added)
    }

    /// Points sent in a request, compared after the JSON round trip: a double can come back one ULP off
    /// (0.04651162790697672 for 0.046511627906976716), so each coordinate within 1e-12 -- never a
    /// looser check on how many points there are. A single `[Double]` (a rect) is passed as `[rect]`.
    private func assertClose(
        _ sent: Any?, _ expected: [[Double]], _ message: String = "", file: StaticString = #filePath, line: UInt = #line
    ) {
        guard let got = (sent as? [[Double]]) ?? (sent as? [Double]).map({ [$0] }) else {
            return XCTFail("not points: \(String(describing: sent)) \(message)", file: file, line: line)
        }
        XCTAssertEqual(got.map(\.count), expected.map(\.count), message, file: file, line: line)
        for (gotPoint, wantPoint) in zip(got, expected) {
            for (gotValue, wantValue) in zip(gotPoint, wantPoint) {
                XCTAssertEqual(gotValue, wantValue, accuracy: 1e-12, message, file: file, line: line)
            }
        }
    }

    /// A page point within an annotation's bounds, edges included.
    private func isInside(_ point: CGPoint, _ rect: CGRect) -> Bool {
        point.x >= rect.minX && point.x <= rect.maxX && point.y >= rect.minY && point.y <= rect.maxY
    }

    /// One point shape, for the rewrite above (the recorded page has no extra shapes).
    private func makePointShape() throws -> AnchorShapeValue {
        AnchorShapeValue(generated: Components.Schemas.AnchorShape(kind: .point, points: [[0.5, 0.5]]))
    }

    /// THE JOINT of `source.textedit.*` (13b): the bodies the served Reader page's OWN script posted
    /// through its own `notify` on the imported Syriac page (recorded by
    /// `test_the_served_page_s_own_messages_are_recorded_for_the_app_s_bridge`, regenerated from the page
    /// every run) go through the bridge's own parse (`ReaderTextEdit.message(from:)`) and
    /// `ReaderTextEditRunner` -- exactly what `applyTextEdit` runs -- and become the requests the engine
    /// takes: a typing run is `representation.create` correcting, and checked against, the reading typed
    /// over; Keep Mine is the same words against what counts now; Return is `segment.split` at the
    /// caret, checked against the version read; deleting every word is an empty reading, never a delete.
    /// Breaks if the page and the app stop agreeing on a message, which each side's own tests cannot see.
    func testTheServedPagesOwnMessagesBecomeTheRequestsTheEngineTakes() async throws {
        let store = try await loadedStore()
        RecordedEngine.readingsReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-readings.json")
        )
        let posted = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.page-messages.json")
        )) as? [[String: Any]])
        XCTAssertEqual(posted.compactMap { $0["kind"] as? String }, ["readingEdit", "readingEdit", "lineSplit", "readingEdit"])
        let client = try XCTUnwrap(storeClient)
        let runner = ReaderTextEditRunner(
            actionsService: ActionsService(client: client), segmentService: SegmentService(ficheroClient: client),
            undoManager: nil, refreshPage: { _ in }
        )
        RecordedEngine.invoked = []
        RecordedEngine.invokeResult = #"{"id":"rep-0009"}"#
        var answers: [String] = []
        for body in posted {
            let edit = try XCTUnwrap(ReaderTextEdit.message(from: body), "the app reads every message the page posts")
            let answer = await runner.apply(edit)
            answers.append(try XCTUnwrap(answer).script)
        }

        let sent = try RecordedEngine.invoked.map { try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
        XCTAssertEqual(
            sent.compactMap { $0["name"] as? String },
            ["representation.create", "representation.create", "segment.split", "representation.create"],
            "no message ever becomes a segment delete: deleting words is a reading"
        )
        let params = sent.compactMap { $0["params"] as? [String: Any] }
        for (index, basis) in [(0, "rep-0001"), (1, "rep-0002")] {
            XCTAssertEqual(params[index]["document_id"] as? String, "doc-0001")
            XCTAssertEqual(params[index]["segment_id"] as? String, "seg-0003")
            XCTAssertEqual(params[index]["content"] as? String, posted[index]["text"] as? String, "the words typed")
            XCTAssertEqual(params[index]["corrects_representation_id"] as? String, basis)
            XCTAssertEqual(params[index]["expected_counting_id"] as? String, basis, "checked against what the page read")
        }
        let line = try XCTUnwrap(store.segments(documentId: "doc-0001").first { $0.id == "seg-0003" })
        XCTAssertEqual(params[2]["segment_id"] as? String, "seg-0003")
        XCTAssertEqual(params[2]["at_offset"] as? Int, posted[2]["offset"] as? Int, "the caret, in the engine's code points")
        XCTAssertEqual(params[2]["expected_version"] as? Int, line.version)
        XCTAssertEqual(params[3]["content"] as? String, "", "every word deleted is an empty reading; the line stays")
        XCTAssertEqual(params[3]["segment_id"] as? String, "seg-0003")
        XCTAssertTrue(answers.allSatisfy { $0.hasPrefix("window.fichero?.lineCommitted?.(") }, "the page is answered each time")
        let first = try XCTUnwrap(answers.first)
        let told = try XCTUnwrap(JSONSerialization.jsonObject(
            with: Data(first.dropFirst("window.fichero?.lineCommitted?.(".count).dropLast(2).utf8)
        ) as? [String: Any])
        XCTAssertEqual(told["representationId"] as? String, "rep-0009", "the run's reading, for the next run's basis")
    }

    /// `source.editor.draw-shapes` end to end (#4941), on the imported Syriac page: with the one Shape
    /// tool set to Polygon, clicking points and then the first one closes the shape, and the request is
    /// `segment.create` of a REGION with that polygon and the rect it bounds, on the shown pass, naming
    /// the pass's own picture; set to Baseline, the clicked points are a LINE anchored by its baseline
    /// as an open path, with no rect or outline invented; each is ⌘Z-able by its audit id -- the exact
    /// calls the engine test proved land and keep the page drawable. A drawn line with a flat baseline
    /// is still given a box to be clicked by. Breaks if a drawing is sent as something else, lands on
    /// another pass, or cannot be clicked once made.
    func testTheShapeToolsPolygonAndBaselineCreateSegmentsWithUndo() async throws {
        let store = try await loadedStore()
        let selected = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        let onPass = store.segments(documentId: "doc-0001").first { $0.passId == selected.passId }
        let reach = [0.004, 0.004]
        var clicked: [[Double]] = [[0.1, 0.1], [0.3, 0.1], [0.3, 0.2]]
        XCTAssertFalse(SegmentShapes.closes(Array(clicked.prefix(2)), at: [0.1, 0.1], tolerance: reach), "three points first")
        clicked.append([0.1, 0.2])
        XCTAssertTrue(SegmentShapes.closes(clicked, at: [0.1005, 0.0998], tolerance: reach), "a click on the first point closes")

        let polygon = try SegmentShapes.create(
            .polygon, points: clicked, documentId: "doc-0001", passId: selected.passId, onPass: onPass
        ).get()
        let baselinePoints = [[0.2, 0.6], [0.5, 0.6], [0.8, 0.6]]
        let baseline = try SegmentShapes.create(
            .baseline, points: baselinePoints, documentId: "doc-0001", passId: selected.passId, onPass: onPass
        ).get()
        XCTAssertEqual(SegmentShapes.create(.baseline, points: [[0.2, 0.6]], documentId: "doc-0001",
                                            passId: selected.passId, onPass: onPass), .failure(.tooFew))
        try await sendDrawings([.init(call: polygon, name: "Draw Polygon", points: clicked),
                                .init(call: baseline, name: "Draw Baseline", points: baselinePoints)],
                               passId: selected.passId, onPass: onPass, store: store)

        var drawnLine = try XCTUnwrap(onPass)
        drawnLine.anchor.rect = nil
        drawnLine.anchor.polygon = nil
        drawnLine.anchor.shapes = [AnchorShapeValue(generated: Components.Schemas.AnchorShape(kind: .path, points: baselinePoints))]
        drawnLine.baseline = baselinePoints
        let box = try XCTUnwrap(SegmentShapes.displayBox(for: drawnLine))
        XCTAssertEqual(box[3], 0.004, accuracy: 1e-9, "a flat baseline is still clickable")
        XCTAssertEqual(box[2], 0.6, accuracy: 1e-9)
    }

    /// One finished drawing: the call it makes, its undo name, the points clicked.
    private struct Drawing {
        let call: SegmentEdit.Call
        let name: String
        let points: [[Double]]
    }

    /// The drawings sent, as the host sends them (`SegmentEditRunner`), and what the engine was asked.
    private func sendDrawings(
        _ drawings: [Drawing],
        passId: String, onPass: Segment?, store: SegmentStore
    ) async throws {
        let (clicked, baselinePoints) = (drawings[0].points, drawings[1].points)
        RecordedEngine.invoked = []
        RecordedEngine.undone = []
        let manager = UndoManager()
        manager.groupsByEvent = false
        let runner = SegmentEditRunner(actionsService: ActionsService(client: try XCTUnwrap(storeClient)), store: store)
        for drawing in drawings {
            manager.beginUndoGrouping()
            try await runner.run(drawing.call, documentId: "doc-0001", actionName: drawing.name, undoManager: manager)
            manager.endUndoGrouping()
        }
        let sent = try RecordedEngine.invoked.map { try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
        XCTAssertEqual(sent.compactMap { $0["name"] as? String }, ["segment.create", "segment.create"])
        let params = sent.compactMap { $0["params"] as? [String: Any] }
        XCTAssertEqual(params.compactMap { $0["pass_id"] as? String }, [passId, passId], "on the shown pass")
        XCTAssertEqual(params.compactMap { $0["kind"] as? String }, ["region", "line"])
        let regionAnchor = try XCTUnwrap(params[0]["anchor"] as? [String: Any])
        assertClose(regionAnchor["polygon"], clicked)
        assertClose(regionAnchor["rect"], [SegmentShapes.bounds(clicked)])
        XCTAssertEqual(regionAnchor["space"] as? String, onPass?.anchor.space, "the pass's own picture")
        let lineAnchor = try XCTUnwrap(params[1]["anchor"] as? [String: Any])
        assertClose(params[1]["baseline"], baselinePoints)
        XCTAssertNil(lineAnchor["rect"], "no box invented for a baseline")
        XCTAssertNil(lineAnchor["polygon"], "no outline invented for a baseline")
        let path = try XCTUnwrap((lineAnchor["shapes"] as? [[String: Any]])?.first)
        XCTAssertEqual(path["kind"] as? String, "path")
        XCTAssertEqual(manager.undoActionName, "Draw Baseline")
        manager.undo()
        for _ in 0..<200 where RecordedEngine.undone.isEmpty { try await Task.sleep(nanoseconds: 10_000_000) }
        XCTAssertEqual(RecordedEngine.undone, ["audit-2"], "⌘Z undoes the last drawing by its own audit id")
    }

    /// `source.editor.reshape` for an anchor's extra shapes, and the arrow-key nudge, on a line of the
    /// recorded Syriac page given a path and a point (the engine test makes the same and proves this exact
    /// update lands): both are drawn and get handles; the path's point is dragged and the point shape --
    /// which takes no new points and cannot be removed -- nudged one image pixel (ten with ⇧); the edit
    /// is `segment.update` sending back every shape, the changed one changed and the rest as they were,
    /// checked against the version read. Breaks if a rewrite drops a shape, a nudge moves by anything but
    /// a pixel, or a point can be added to or removed.
    func testReshapingAnAnchorsPathAndPointAndNudgingByAPixel() async throws {
        let store = try await loadedStore()
        var line = try XCTUnwrap(store.segments(documentId: "doc-0001").first { $0.id == "seg-0003" })
        let path = [[0.2, 0.6], [0.5, 0.6], [0.8, 0.61]]
        line.anchor.shapes = [
            AnchorShapeValue(generated: Components.Schemas.AnchorShape(kind: .path, points: path)),
            AnchorShapeValue(generated: Components.Schemas.AnchorShape(kind: .point, points: [[0.9, 0.62]]))
        ]
        let drawn = SegmentShapes.drawn(for: line)
        XCTAssertEqual(drawn, [
            .polygon(try XCTUnwrap(line.anchor.polygon)), .path(path, shape: 0), .point([0.9, 0.62], shape: 1),
            .baseline(try XCTUnwrap(line.baseline))
        ], "outline, each extra shape by its index, then the baseline")
        let reach = [0.004, 0.004]
        XCTAssertEqual(SegmentShapes.handle(at: [0.5, 0.6], in: drawn, tolerance: reach), .vertex(.shape(0, .path), 1))
        XCTAssertEqual(SegmentShapes.handle(at: [0.9, 0.62], in: drawn, tolerance: reach), .vertex(.shape(1, .point), 0))
        XCTAssertTrue(SegmentShapes.sideMidpoints([[0.9, 0.62]], .shape(1, .point)).isEmpty, "a point takes no new points")
        XCTAssertNil(SegmentShapes.removing([[0.9, 0.62]], index: 0, .shape(1, .point)), "and is never removed")

        let nudged = SegmentShapes.nudging([[0.9, 0.62]], index: 0, byPixels: [1, 0], imageSize: [1969, 2365])
        XCTAssertEqual(nudged[0][0], 0.9 + 1 / 1969, accuracy: 1e-12, "one image pixel")
        let fast = SegmentShapes.nudging([[0.9, 0.62]], index: 0, byPixels: [0, 10], imageSize: [1969, 2365])
        XCTAssertEqual(fast[0][1], 0.62 + 10 / 2365, accuracy: 1e-12, "ten with ⇧")

        let movedPath = SegmentShapes.moving(path, index: 1, to: [0.5, 0.58])
        let call = try SegmentShapes.reshape(line, .shape(0, .path), to: movedPath).get()
        RecordedEngine.invoked = []
        try await SegmentEditRunner(actionsService: ActionsService(client: try XCTUnwrap(storeClient)), store: store).run(
            call, documentId: "doc-0001", actionName: "Reshape Segment", undoManager: nil
        )
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        let params = try XCTUnwrap(sent["params"] as? [String: Any])
        XCTAssertEqual(params["expected_version"] as? Int, line.version)
        let anchor = try XCTUnwrap(params["anchor"] as? [String: Any])
        let shapes = try XCTUnwrap(anchor["shapes"] as? [[String: Any]])
        XCTAssertEqual(shapes.compactMap { $0["kind"] as? String }, ["path", "point"], "every shape sent back, in order")
        assertClose(shapes[0]["points"], movedPath)
        assertClose(shapes[1]["points"], [[0.9, 0.62]], "the other shape as it was")
        assertClose(anchor["polygon"], try XCTUnwrap(line.anchor.polygon), "the outline carried")
    }

    /// "Continue a Flow Here" end to end (#5160 residue, `source.segment.flow`), over the recorded answer
    /// for the second of two pages of one Syriac source, with a flow made on the first: the picker is
    /// offered that flow as ending on an earlier page; continuing it places THIS page's segments at the
    /// flow's end, in the page's own order, one `POST …/place {segment_id, at_end: true}` each -- the exact
    /// calls the recorder proved land and stop the flow being offered again. Breaks if the flow is not
    /// offered, a segment is placed out of order or twice, or a place is not at the end.
    func testAFlowFromAnEarlierPageIsOfferedAndContinuingItPlacesThisPagesSegmentsAtTheEnd() async throws {
        let store = try await loadedStore()
        RecordedEngine.flowsOntoReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.flows-onto-next-page.json")
        )
        let service = ReadingOrderService(ficheroClient: try XCTUnwrap(storeClient))
        let offered = try await service.flowsOnto(documentId: "doc-0002")
        XCTAssertEqual(offered.flows.map(\.title), ["Into the next page (earlier page)"])
        XCTAssertEqual(offered.flows.first?.lastPageId, "doc-0001")
        XCTAssertEqual(offered.withheld, 0)

        let shown = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        let segments = store.segments(documentId: "doc-0001")
        let ids = ReadingOrderChoice.continuation(of: segments, onPass: shown.passId)
        XCTAssertEqual(ids.count, 16)
        XCTAssertEqual(ids, segments.filter { $0.passId == shown.passId }
            .sorted { ($0.boxIndex ?? 0) < ($1.boxIndex ?? 0) }.map(\.id), "the page's own order")
        XCTAssertEqual(Set(ids).count, ids.count, "each segment once")

        RecordedEngine.placed = []
        for id in ids.prefix(2) {
            _ = try await service.placeAtEnd(orderId: "order-0003", segmentId: id)
        }
        let sent = try RecordedEngine.placed.map { try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
        XCTAssertEqual(sent.compactMap { $0["segment_id"] as? String }, Array(ids.prefix(2)))
        XCTAssertEqual(sent.compactMap { $0["at_end"] as? Bool }, [true, true], "at the flow's end")
    }

    /// `source.textedit.stale-keeps-your-words`, "out of reach of the engine the text is read-only" (13b):
    /// the served page's own typing message (the joint's recording) goes through the bridge's parse and
    /// `ReaderTextEditRunner` while the engine cannot be reached -- the transport fails, no HTTP answer --
    /// and the page is told `unreachable: true` with short words, never `ok`, and the coordinator is told
    /// why so it can tell the page the engine is gone and watch for its return. An HTTP refusal is not
    /// "out of reach". Breaks if a lost connection reads as a refusal (the page would re-read from an
    /// engine that is not there) or as success (the words would be dropped as sent).
    func testATypedLineThatCannotReachTheEngineIsHeldNotLost() async throws {
        _ = try await loadedStore()
        let posted = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.page-messages.json")
        )) as? [[String: Any]])
        let client = try XCTUnwrap(storeClient)
        let runner = ReaderTextEditRunner(
            actionsService: ActionsService(client: client), segmentService: SegmentService(ficheroClient: client),
            undoManager: nil, refreshPage: { _ in XCTFail("no engine to re-read from") }
        )
        RecordedEngine.invokeUnreachable = true
        let typed = try XCTUnwrap(ReaderTextEdit.message(from: posted[0]))
        let fetched = await runner.apply(typed)
        let answer = try XCTUnwrap(fetched)
        XCTAssertEqual(answer.unreachableReason, "connection refused")
        let told = try XCTUnwrap(JSONSerialization.jsonObject(
            with: Data(answer.script.dropFirst("window.fichero?.lineCommitted?.(".count).dropLast(2).utf8)
        ) as? [String: Any])
        XCTAssertEqual(told["unreachable"] as? Bool, true)
        XCTAssertEqual(told["ok"] as? Bool, false)
        XCTAssertEqual(told["segmentId"] as? String, "seg-0003")
        XCTAssertEqual(ReaderTextEdit.engineStateScript(reachable: false, reason: "connection refused"),
                       #"window.fichero?.engineState?.({"reachable":false,"reason":"connection refused"});"#)
        XCTAssertEqual(ReaderTextEdit.engineStateScript(reachable: true), #"window.fichero?.engineState?.({"reachable":true});"#)
        XCTAssertNil(ReaderTextEdit.unreachableReason(APIError.httpError(statusCode: 409, message: "stale")),
                     "a refusal reached the engine: not out of reach")

        // The engine comes back on the third ask: the page is told once, and asked about nothing more.
        var asks = 0
        var saidToPage: [String] = []
        await ReaderTextEdit.waitForReturn(
            isBack: { asks += 1; return asks == 3 }, pause: {}, tell: { saidToPage.append($0) }
        )
        XCTAssertEqual(asks, 3)
        XCTAssertEqual(saidToPage, [ReaderTextEdit.engineStateScript(reachable: true)], "told once, when it answers")
    }

    /// `source.textedit.deleting-words-keeps-ink`, its last clause, end to end on the imported Syriac page
    /// (the engine's recorded answers, before and after): a line drawn by its baseline has NO reading, and
    /// is still drawn -- hollow and dashed, by its shapes -- and still picked by a click, listed in the
    /// Segments pane as "No reading", and offered "Type a Reading" in the Inspector; an EMPTIED line (an
    /// empty reading) is not marked. Typing one sends `representation.create` on that segment, and once
    /// the engine has it the mark is gone. Breaks if a reading-less segment is hidden, unclickable, or
    /// confused with an emptied one.
    func testASegmentWithNoReadingIsShownPickedAndListedAsSuchAndTypingOneClearsIt() async throws {
        let store = try await loadedStore()
        let recorded = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.no-reading.json")
        )) as? [String: Any])
        RecordedEngine.body = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["before"]))
        await store.load(documentId: "doc-0001", force: true)
        let segments = store.segments(documentId: "doc-0001")
        let drawn = try XCTUnwrap(segments.first { $0.id == "seg-drawn-0001" })
        let emptied = try XCTUnwrap(segments.first { $0.id == "seg-0012" })
        XCTAssertTrue(SegmentsPane.lacksReading(drawn))
        XCTAssertFalse(SegmentsPane.lacksReading(emptied), "an emptied line has a reading: an empty one")

        let selected = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store), "the page still draws")
        let box = selected.geometry.boxes[try XCTUnwrap(drawn.boxIndex)]
        XCTAssertTrue(box.noReading, "drawn hollow and dashed, never hidden")
        XCTAssertFalse(box.shapes.isEmpty, "as its baseline, not a guessed box")
        XCTAssertFalse(selected.geometry.boxes[try XCTUnwrap(emptied.boxIndex)].noReading)
        let center = CGPoint(x: (box.bbox[0] + box.bbox[2] / 2) * 1000, y: (box.bbox[1] + box.bbox[3] / 2) * 1000)
        let picked = RegionHitTesting.pick(
            at: center, boxes: [box.bbox], in: CGSize(width: 1000, height: 1000), visible: CGRect(x: 0, y: 0, width: 1, height: 1)
        )
        XCTAssertEqual(picked, 0, "a click on it picks it")
        XCTAssertTrue(SegmentsPane.rowLabel(drawn, at: 16).hasSuffix(" · No reading"), "listed with the mark")
        XCTAssertFalse(SegmentsPane.rowLabel(emptied, at: 3).hasSuffix(" · No reading"))

        RecordedEngine.invoked = []
        try await AuditedAction.run(
            "representation.create",
            params: NewReadingParams(documentId: "doc-0001", segmentId: drawn.id, kind: "transcription",
                                     content: "ܫܠܡܐ", correctsRepresentationId: nil),
            actionName: "Type a Reading", actionsService: ActionsService(client: try XCTUnwrap(storeClient)), undoManager: nil
        )
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: XCTUnwrap(RecordedEngine.invoked.first)) as? [String: Any])
        let params = try XCTUnwrap(sent["params"] as? [String: Any])
        XCTAssertEqual(params["segment_id"] as? String, "seg-drawn-0001")
        XCTAssertEqual(params["content"] as? String, "ܫܠܡܐ")
        XCTAssertNil(params["corrects_representation_id"], "nothing to correct: it had no reading")

        RecordedEngine.body = try JSONSerialization.data(withJSONObject: XCTUnwrap(recorded["after"]))
        await store.load(documentId: "doc-0001", force: true)
        let typed = try XCTUnwrap(store.segments(documentId: "doc-0001").first { $0.id == "seg-drawn-0001" })
        XCTAssertFalse(SegmentsPane.lacksReading(typed), "the mark goes once it has a reading")
        XCTAssertEqual(SegmentsPane.rowLabel(typed, at: 16), "Line · ܫܠܡܐ")
        let redrawn = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        XCTAssertFalse(redrawn.geometry.boxes[try XCTUnwrap(typed.boxIndex)].noReading)
    }

    /// Shapes on PDF pages (#5163 residue), end to end: the recorded Syriac lines (whose outlines and
    /// baselines the engine test proves reach a PDF page as the file drew them) drawn on the corpus's real
    /// PDF page (`dialogo_lengua_page_18.pdf`, opened with PDFKit) by the renderer's own builder
    /// (`PDFShapeAnnotations.make`): each line is two ink annotations -- its closed outline and its
    /// heavier baseline -- placed where the page's crop box and rotation put the file's points; a segment
    /// with no reading is dashed; a box with no shapes of its own is left to the square it always was.
    /// Breaks if a PDF page draws boxes where an image draws shapes, or puts a point off the ink.
    func testAPDFPageDrawsALinesOutlineAndBaselineAsThemselves() async throws {
        let store = try await loadedStore()
        let selected = try XCTUnwrap(SegmentDisplay.selected(for: "doc-0001", store: store))
        let line = try XCTUnwrap(store.segments(documentId: "doc-0001").first { $0.id == "seg-0003" })
        let box = selected.geometry.boxes[try XCTUnwrap(line.boxIndex)]
        let pdf = try XCTUnwrap(PDFDocument(url: fixtures().appendingPathComponent("dialogo_lengua_page_18.pdf")))
        let page = try XCTUnwrap(pdf.page(at: 0))
        let crop = page.bounds(for: .cropBox)

        let drawn = try XCTUnwrap(PDFShapeAnnotations.make(for: box, on: page, userName: "fichero.ocr-box"))
        XCTAssertEqual(drawn.count, 2, "the outline and the baseline")
        XCTAssertEqual(drawn.compactMap(\.type), ["Ink", "Ink"])
        let polygon = try XCTUnwrap(line.anchor.polygon)
        let baseline = try XCTUnwrap(line.baseline)
        let firstCorner = try XCTUnwrap(PDFRegionGeometry.pagePoint(normalized: polygon[0], rotation: page.rotation, crop: crop))
        XCTAssertTrue(isInside(firstCorner, drawn[0].bounds), "the outline sits on the file's points on this page")
        let baselineStart = try XCTUnwrap(PDFRegionGeometry.pagePoint(normalized: baseline[0], rotation: page.rotation, crop: crop))
        XCTAssertTrue(isInside(baselineStart, drawn[1].bounds))
        XCTAssertEqual(drawn[1].border?.lineWidth, 2, "the baseline heavier than the outline")
        XCTAssertEqual(drawn[0].border?.lineWidth, 1)
        XCTAssertTrue(drawn.allSatisfy { $0.userName == "fichero.ocr-box" }, "swept with the boxes")

        // The mapping itself, on this page and on a rotated one: the same rule as the boxes'.
        XCTAssertEqual(PDFRegionGeometry.pagePoint(normalized: [0.25, 0.25], rotation: 0, crop: crop),
                       CGPoint(x: crop.minX + 0.25 * crop.width, y: crop.minY + 0.75 * crop.height))
        let quarter = PDFRegionGeometry.unrotated(normalized: [0.25, 0.25, 0, 0], rotation: 90)
        XCTAssertEqual(PDFRegionGeometry.pagePoint(normalized: [0.25, 0.25], rotation: 90, crop: crop),
                       CGPoint(x: crop.minX + quarter[0] * crop.width, y: crop.minY + (1 - quarter[1]) * crop.height))

        var unread = box
        unread.noReading = true
        let dashed = try XCTUnwrap(PDFShapeAnnotations.make(for: unread, on: page, userName: "fichero.ocr-box"))
        XCTAssertTrue(dashed.allSatisfy { $0.border?.style == .dashed }, "no reading: dashed, never hidden")
        var plain = box
        plain.shapes = []
        XCTAssertNil(PDFShapeAnnotations.make(for: plain, on: page, userName: "fichero.ocr-box"), "a box stays a square")
    }

    /// A drawn line lands in its region (`source.editor.draw-shapes`), on the recorded Syriac page: a
    /// baseline drawn at the foot of region 2 is placed in region 2 -- the region holding MOST of it -- and
    /// the create sends it as the parent (the engine test proves that makes region 2's last line, one undo
    /// taking both); its path reads Page › Region › Line. A baseline outside every region, or only half in
    /// one, stays at page level with no guess, and its path says so (Page › Line). Breaks if a line is
    /// orphaned inside a region, or put in one it barely touches.
    func testALineDrawnInsideARegionIsCreatedAsThatRegionsLine() async throws {
        let store = try await loadedStore()
        let segments = store.segments(documentId: "doc-0001")
        let regions = segments.filter { $0.kind == "region" }
            .sorted { (($0.anchor.rect?[1] ?? 0), ($0.anchor.rect?[0] ?? 0)) < (($1.anchor.rect?[1] ?? 0), ($1.anchor.rect?[0] ?? 0)) }
        let region = regions[1]
        let rect = try XCTUnwrap(region.anchor.rect)
        let baseline = [[rect[0] + 0.1 * rect[2], rect[1] + 0.97 * rect[3]], [rect[0] + 0.9 * rect[2], rect[1] + 0.975 * rect[3]]]
        XCTAssertEqual(SegmentShapes.containingRegion(for: baseline, among: segments)?.id, region.id, "the region it is drawn in")
        XCTAssertNil(SegmentShapes.containingRegion(for: [[0.001, 0.001], [0.01, 0.001]], among: segments), "outside every region")
        let straddling = [[rect[0] - 0.6 * rect[2], rect[1] + 0.5 * rect[3]], [rect[0] + 0.3 * rect[2], rect[1] + 0.5 * rect[3]]]
        XCTAssertNil(SegmentShapes.containingRegion(for: straddling, among: segments), "a third inside is not most of it")

        let call = try SegmentShapes.create(
            .baseline, points: baseline, documentId: "doc-0001", passId: region.passId, onPass: region, parentSegmentId: region.id
        ).get()
        let sent = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(call.params)) as? [String: Any])
        XCTAssertEqual(sent["parent_segment_id"] as? String, region.id)
        XCTAssertEqual(sent["kind"] as? String, "line")
        let pageLevel = try SegmentShapes.create(
            .baseline, points: baseline, documentId: "doc-0001", passId: region.passId, onPass: region, parentSegmentId: nil
        ).get()
        let unparented = try XCTUnwrap(JSONSerialization.jsonObject(with: JSONEncoder().encode(pageLevel.params)) as? [String: Any])
        XCTAssertNil(unparented["parent_segment_id"], "no region: no parent sent, never a guessed one")

        var drawn = try XCTUnwrap(segments.first { $0.kind == "line" })
        drawn.id = "seg-drawn"
        drawn.parentSegmentId = region.id
        XCTAssertEqual(InspectorPath.to("seg-drawn", in: segments + [drawn])?.crumbs.map(\.label), ["Region", "Line"])
        drawn.parentSegmentId = nil
        XCTAssertEqual(InspectorPath.to("seg-drawn", in: segments + [drawn])?.crumbs.map(\.label), ["Line"],
                       "at page level, and the path says so")
    }

    /// `source.textedit.deleting-words-keeps-ink` end to end, the app's half: deleting words from the
    /// imported Syriac page's first line -- down to nothing at all -- is a NEW READING without them,
    /// through the calls the Reader's coordinator makes. No segment action is ever sent: the line and
    /// its box stay; deleting a segment is the Source view's own named command.
    func testDeletingWordsIsANewReadingAndNeverTouchesTheSegments() async throws {
        let store = try await loadedStore()
        let line = try XCTUnwrap(store.segments(documentId: "doc-0001").first { $0.id == "seg-0003" })
        let words = (line.text ?? "").split(separator: " ")
        XCTAssertGreaterThan(words.count, 2)
        let actions = ActionsService(client: try XCTUnwrap(storeClient))
        for text in [words.dropLast().joined(separator: " "), ""] {
            let edit = try XCTUnwrap(ReaderTextEdit.message(from: [
                "kind": "readingEdit", "pageId": "doc-0001", "segmentId": line.id, "text": text,
                "previous": line.text ?? "", "basedOn": "rep-0001"
            ]))
            try await AuditedAction.run(
                "representation.create", params: try XCTUnwrap(ReaderTextEdit.newReading(for: edit)),
                actionName: "Typing", actionsService: actions, undoManager: nil
            )
        }
        let sent = try RecordedEngine.invoked.map { try XCTUnwrap(JSONSerialization.jsonObject(with: $0) as? [String: Any]) }
        XCTAssertEqual(sent.compactMap { $0["name"] as? String }, ["representation.create", "representation.create"])
        let contents = sent.compactMap { ($0["params"] as? [String: Any])?["content"] as? String }
        XCTAssertEqual(contents, [words.dropLast().joined(separator: " "), ""], "the words gone from the reading, down to an empty line")
        XCTAssertTrue(sent.allSatisfy { ($0["params"] as? [String: Any])?["segment_id"] as? String == line.id })
        XCTAssertEqual(store.segments(documentId: "doc-0001").filter { $0.id == line.id }.count, 1, "the line is still there")
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
