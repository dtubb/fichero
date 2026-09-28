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

        // swiftlint:disable:next static_over_final_class
        override class func canInit(with request: URLRequest) -> Bool {
            guard request.url?.host == "127.0.0.1", let path = request.url?.path else { return false }
            return path.hasPrefix("/api/segments/document/") || path == "/api/annotations"
                || path.hasPrefix("/api/actions/") || path.hasPrefix("/api/segments/passes/")
                || (path.hasPrefix("/api/segments/") && path.hasSuffix("/readings"))
                || path == "/api/source-settings/resolve" || path.hasPrefix("/api/hands")
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

        private static func actionReply(auditId: String) -> Data {
            Data(#"{"ok":true,"result":{},"audit_id":"\#(auditId)","changed_domains":["segment"]}"#.utf8)
        }

        // swiftlint:disable:next static_over_final_class
        override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

        override func startLoading() {
            let path = request.url?.path ?? ""
            let isAnnotation = path == "/api/annotations"
            if isAnnotation { Self.annotationRequests.append(Self.bodyOf(request)) }
            var actionBody: Data?
            if path == "/api/hands" {
                actionBody = Self.handsReply
            } else if path.hasPrefix("/api/hands/segment/") {
                actionBody = Self.attributionsReply
            } else if path == "/api/source-settings/resolve" {
                actionBody = Self.settingsReply
            } else if path.hasPrefix("/api/segments/"), path.hasSuffix("/readings") {
                actionBody = Self.readingsReply
            } else if path.hasPrefix("/api/segments/passes/"), path.hasSuffix("/original") {
                actionBody = Self.originalReply
            } else if path == "/api/actions/invoke" {
                Self.invoked.append(Self.bodyOf(request))
                actionBody = Self.actionReply(auditId: "audit-\(Self.invoked.count)")
            } else if path.hasPrefix("/api/actions/audit/"), path.hasSuffix("/undo") {
                let auditId = path.split(separator: "/").dropLast().last.map(String.init) ?? ""
                Self.undone.append(auditId)
                actionBody = Self.actionReply(auditId: "undo-of-\(auditId)")
            }
            guard let url = request.url,
                  let response = HTTPURLResponse(
                      url: url, statusCode: isAnnotation ? 422 : 200, httpVersion: "HTTP/1.1",
                      headerFields: ["Content-Type": "application/json"]
                  ) else {
                client?.urlProtocol(self, didFailWithError: URLError(.badURL))
                return
            }
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: actionBody ?? (isAnnotation ? Data("{}".utf8) : Self.body))
            client?.urlProtocolDidFinishLoading(self)
        }

        override func stopLoading() {}

        /// URLSession hands a protocol its body as a stream, not as `httpBody`.
        private static func bodyOf(_ request: URLRequest) -> Data {
            if let body = request.httpBody { return body }
            guard let stream = request.httpBodyStream else { return Data() }
            stream.open()
            defer { stream.close() }
            var data = Data()
            var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable {
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

        let corpus = try AppSource.root().deletingLastPathComponent().deletingLastPathComponent()
            .appendingPathComponent("fichero-server/tests/unit/formats/fixtures/corpus/escriptorium_syriac_onb-syr1-0001.page.xml")
        let fileBytes = try Data(contentsOf: corpus)
        RecordedEngine.originalReply = try JSONSerialization.data(withJSONObject: [
            "pass_id": entry.passId, "file_name": "escriptorium_syriac_onb-syr1-0001.page.xml",
            "import_format": "pagexml", "media_type": "application/xml",
            "content_base64": fileBytes.base64EncodedString()
        ])
        let original = try await XCTUnwrap(
            SegmentService(ficheroClient: XCTUnwrap(storeClient)).original(passId: entry.passId)
        )
        XCTAssertEqual(original.bytes, fileBytes, "Show Original is the file byte for byte")
        XCTAssertEqual(original.text, String(data: fileBytes, encoding: .utf8), "shown as the file's own text")
    }

    /// #5153 end to end: on the imported Syriac page's first line -- the file's reading and a
    /// person's correction, neither counting (the engine's recorded answer) -- the Text section reads
    /// both through `SegmentService.readings`, says nothing counts, and "Make This Count" on the
    /// correction sends `reading.choose` with its id; ⌘Z undoes that choice by its own audit id.
    func testChoosingTheCorrectionOnAnImportedLineSendsReadingChooseAndUndoes() async throws {
        _ = try await loadedStore()
        RecordedEngine.readingsReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-readings.json")
        )
        let service = SegmentService(ficheroClient: try XCTUnwrap(storeClient))
        let text = try await XCTUnwrap(service.readings(segmentId: "seg-0003"))
        XCTAssertEqual(text.readings.map(\.id), ["rep-0001", "rep-0002"])
        XCTAssertEqual(text.counting["transcription"]?.why, .noneCounts)
        XCTAssertEqual(text.readings[1].correctsId, "rep-0001", "the correction says what it corrects")

        let params = try XCTUnwrap(ReadingChoice.choose(text.readings[1], of: "seg-0003", in: text))
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
                       ["segment_id": "seg-0003", "kind": "transcription", "representation_id": "rep-0002"])
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
    /// over the engine's recorded answer. What the section shows is exactly what the engine says --
    /// including that "English" is only a FALLBACK and the script is not determined (#5176: the engine
    /// does not yet read the line's own Syriac text). A fallback is never shown as a fact.
    func testTheLanguageSectionShowsTheEnginesAnswerAndWhereEachFactCameFrom() async throws {
        _ = try await loadedStore()
        RecordedEngine.settingsReply = try Data(
            contentsOf: fixtures().appendingPathComponent("syriac_onb-syr1-0001.first-line-settings.json")
        )
        let settings = try await SegmentService(ficheroClient: try XCTUnwrap(storeClient))
            .resolvedSettings(segmentId: "seg-0003")
        let rows = Dictionary(uniqueKeysWithValues: InspectorLanguage.rows(settings).map { ($0.key, $0) })
        XCTAssertEqual(rows["language"]?.value, "English")
        XCTAssertEqual(rows["language"]?.origin, "a fallback")
        XCTAssertEqual(rows["script"]?.value, "Not determined")
        XCTAssertEqual(rows["direction"]?.value, "Left to Right")
        XCTAssertEqual(rows["direction"]?.origin, "from the script")
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
            "hand.unattribute", params: HandUnattributeParams(attributionId: rows[0].attributionId),
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
