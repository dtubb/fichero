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
        /// The `result` an invoke answers with (the engine's is per action; `{}` unless a test says).
        nonisolated(unsafe) static var invokeResult = "{}"

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool {
            guard request.url?.host == "127.0.0.1", let path = request.url?.path else { return false }
            return path.hasPrefix("/api/segments/document/") || path == "/api/annotations"
                || path.hasPrefix("/api/actions/") || path.hasPrefix("/api/segments/passes/")
                || (path.hasPrefix("/api/segments/") && path.hasSuffix("/readings"))
                || path == "/api/source-settings/resolve" || path.hasPrefix("/api/hands")
                || path.hasPrefix("/api/editorial/") || path.hasPrefix("/api/signs")
                || path.hasPrefix("/api/letterforms") || path.hasPrefix("/api/links/")
                || (path.hasPrefix("/api/segments/") && path.hasSuffix("/reference"))
                || path == "/api/rights/effective"
                || (path.hasPrefix("/api/segments/") && path.hasSuffix("/statements"))
                || path.hasPrefix("/api/reading-orders/")
                || path.split(separator: "/").count == 3 && path.hasPrefix("/api/segments/")
                || (path.hasPrefix("/api/segments/") && path.hasSuffix("/picture"))
        }

        /// What `GET /api/hands` and `GET /api/hands/segment/{id}` answer (set by the test that asks).
        nonisolated(unsafe) static var handsReply = Data()
        nonisolated(unsafe) static var attributionsReply = Data()

        /// What `GET /api/source-settings/resolve` answers (set by the test that asks).
        nonisolated(unsafe) static var settingsReply = Data()

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
            } else if path.hasPrefix("/api/reading-orders/document/") {
                actionBody = Self.ordersReply
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
            invokeResult = "{}"
            handsReply = Data()
            attributionsReply = Data()
            settingsReply = Data()
            readingsReply = Data()
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
