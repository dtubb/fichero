import AppKit
@testable import Fichero
import FicheroAPIClient
import Foundation
import Testing

/// The UI verbs (spec: docs/contributor_manual/specs/harness/surfaces-from-openapi.md, #5453):
/// `openapi.ui.verbs-are-the-click` and `openapi.ui.screenshot`. Each App Intent is performed as Shortcuts
/// or a UI test performs it, against the real `LibraryManager`, `WindowState` and `SegmentStore`; only
/// the engine's HTTP answer is recorded. What the window then does with a request (`applyUIVerb`) is the
/// click's own code, which these tests do not repeat.
@MainActor
@Suite(.serialized)
struct UIVerbsTests {
    // MARK: - Fixtures

    /// Answers every request to the test host with the recorded segments route (as `LineRevealTests`).
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
            libraryPath: "/tmp/UIVerbsTests.fichero",
            session: URLSession(configuration: configuration)
        )
        let store = SegmentStore(service: SegmentService(ficheroClient: client))
        await store.load(documentId: "doc-0001")
        return store
    }

    /// A front window, as the last window made key is.
    private func frontWindow() -> WindowState {
        let window = WindowState(libraryId: UUID())
        WindowState.front = window
        return window
    }

    // MARK: - openapi.ui.verbs-are-the-click

    /// WHY: "open a project" must be File ▸ Open's click -- the project opened once (a second open is
    /// the same project, never a duplicate) and shown in the front window -- not a parallel open that
    /// leaves the window on its old project.
    @Test func openProjectIsFileOpen() async throws {
        let manager = LibraryManager.shared
        let defaults = EngineConfig.defaults
        let savedPaths = defaults.stringArray(forKey: LibraryManager.openLibraryPathsKey)
        let savedCurrent = manager.currentLibraryId
        let url = FileManager.default.temporaryDirectory.appendingPathComponent("UIVerbs-\(UUID().uuidString).fichero")
        try FileManager.default.createDirectory(at: url, withIntermediateDirectories: true)
        let window = frontWindow()
        var opened: UUID?
        defer {
            if let opened { manager.closeLibrary(opened) }
            manager.currentLibraryId = savedCurrent
            if let savedPaths { defaults.set(savedPaths, forKey: LibraryManager.openLibraryPathsKey) } else {
                defaults.removeObject(forKey: LibraryManager.openLibraryPathsKey)
            }
            try? FileManager.default.removeItem(at: url)
        }

        var intent = OpenProjectIntent()
        intent.path = url.path
        _ = try await intent.perform()

        let library = try #require(manager.openLibraries.first {
            LibraryManager.canonicalLibraryKey($0.url) == LibraryManager.canonicalLibraryKey(url)
        })
        opened = library.id
        #expect(window.libraryId == library.id, "the front window shows the project")
        #expect(manager.currentLibraryId == library.id)
        _ = try await intent.perform()
        #expect(manager.openLibraries.filter { $0.id == library.id }.count == 1, "opening it again is the same project")
    }

    /// WHY: "open a node" must go through the sidebar's reveal, the seam a click on a crumb or a Segments
    /// row posts, so the sidebar, Preview and Inspector follow it as they follow a click.
    @Test func openNodeIsTheSidebarReveal() async throws {
        var posted: [String: String]?
        let token = NotificationCenter.default.addObserver(forName: .sidebarRevealDocument, object: nil, queue: nil) { note in
            posted = note.userInfo as? [String: String]
        }
        defer { NotificationCenter.default.removeObserver(token) }
        var intent = OpenNodeIntent()
        intent.nodeId = "doc-7"
        _ = try await intent.perform()
        #expect(posted == ["documentId": "doc-7"])
    }

    /// WHY: select, show a pane and show an Inspector tab act on the FRONT window only -- a script
    /// driving one window must not move every other -- and asking twice must act twice (a token).
    @Test func windowVerbsAskTheFrontWindow() async throws {
        let other = WindowState(libraryId: UUID())
        let window = frontWindow()

        var select = SelectNodesIntent()
        select.nodeIds = ["doc-1", "doc-2"]
        _ = try await select.perform()
        #expect(window.uiVerbRequest?.action == .select(["doc-1", "doc-2"]))
        let first = try #require(window.uiVerbRequest?.token)
        _ = try await select.perform()
        #expect(window.uiVerbRequest?.token == first + 1, "asking again acts again")

        var pane = ShowPaneIntent()
        pane.pane = .preview
        _ = try await pane.perform()
        #expect(window.uiVerbRequest?.action == .showPane(.preview))

        var tab = ShowInspectorTabIntent()
        tab.tab = "knowledge graph"
        _ = try await tab.perform()
        #expect(window.uiVerbRequest?.action == .showInspectorTab(.knowledgeGraph))
        #expect(other.uiVerbRequest == nil, "another window is not driven")

        tab.tab = "Settings"
        await #expect(throws: UIVerbs.Failure.unknownInspectorTab("Settings")) { try await tab.perform() }
    }

    /// WHY: with no window, a verb must refuse loudly -- an agent told "done" when nothing could happen
    /// checks a screen that never changed.
    @Test func noWindowRefuses() async throws {
        WindowState.front = nil
        var select = SelectNodesIntent()
        select.nodeIds = ["doc-1"]
        await #expect(throws: UIVerbs.Failure.noWindow) { try await select.perform() }
        await #expect(throws: UIVerbs.Failure.noWindow) { _ = try UIVerbs.revealSegments(["s"], documentId: "d") }
    }

    /// WHY: "reveal a line" must be `WindowState.revealSegments`, the one reveal the Order list's
    /// double-click and the Reader's line click make: the line's box selected in the linked Preview and
    /// zoomed to. And with no Preview it reveals nothing, so the verb answers no ids.
    @Test func revealSegmentsIsTheReadersLineClick() async throws {
        let store = try await loadedStore()
        let shown = try #require(SegmentDisplay.selected(for: "doc-0001", store: store))
        let line = try #require(store.segments(documentId: "doc-0001").first { $0.kind == "line" })
        let box = try #require(line.boxIndex)
        let preview = RegionSelection()
        let window = frontWindow()
        window.offerRegionSelection(preview)

        let revealed = try UIVerbs.revealSegments([line.id], documentId: "doc-0001", store: store)

        #expect(revealed == [line.id])
        #expect(preview.resolvedIndices(in: shown.geometry.boxes) == [box], "the line's box is selected")
        #expect(preview.revealRect == shown.geometry.boxes[box].bbox, "the Preview zooms to it")
        #expect(try UIVerbs.revealSegments([line.id], documentId: "doc-0001", in: WindowState(libraryId: UUID()), store: store)
            .isEmpty, "no linked Preview reveals nothing")

        // Through the intent, the store is the window's project's: a window whose project is not open refuses.
        var intent = RevealSegmentsIntent()
        intent.segmentIds = [line.id]
        intent.documentId = "doc-0001"
        await #expect(throws: UIVerbs.Failure.noLibrary) { try await intent.perform() }
    }

    /// WHY: a script says a pane or tab by name; "reading" is the Reader's own kind name, and a tab may be
    /// said by its title or its case, in any case. A name that is neither must not guess.
    @Test func panesAndTabsByName() {
        #expect(UIPane(named: " Reading ") == .reader)
        #expect(UIPane(named: "INSPECTOR") == .inspector)
        #expect(UIPane(named: "kg") == nil)
        #expect(UIPane.reader.frameKey == PaneKind.reading.rawValue, "the Reader's frame is recorded under its pane kind")
        #expect(InspectorTab(named: "Knowledge Graph") == .knowledgeGraph)
        #expect(InspectorTab(named: "knowledgegraph") == .knowledgeGraph)
        #expect(InspectorTab(named: "info") == .info)
        #expect(InspectorTab(named: "graph") == nil)
    }

    // MARK: - openapi.ui.screenshot

    /// A 320 × 200 window: grey, with a green 100 × 50 box 20 pt from the left and 10 pt from the top.
    private final class Painted: NSView {
        override func draw(_ dirtyRect: NSRect) {
            NSColor.gray.setFill()
            bounds.fill()
            NSColor.green.setFill()
            NSRect(x: 20, y: bounds.height - 10 - 50, width: 100, height: 50).fill()
        }
    }

    private func paintedWindow() -> (NSWindow, WindowState) {
        let window = NSWindow(contentRect: NSRect(x: 0, y: 0, width: 320, height: 200), styleMask: [.borderless],
                              backing: .buffered, defer: false)
        window.isReleasedWhenClosed = false
        window.contentView = Painted(frame: NSRect(x: 0, y: 0, width: 320, height: 200))
        let state = WindowState(libraryId: UUID())
        state.hostWindow = window
        return (window, state)
    }

    private func png(at path: String) throws -> NSBitmapImageRep {
        try #require(NSBitmapImageRep(data: Data(contentsOf: URL(fileURLWithPath: path))))
    }

    /// WHY: the screenshot verb is how an agent checks on screen what it did, and how documentation
    /// pictures are made -- the app draws its own window (no screen-recording prompt), at the window's
    /// full pixel size, into a real PNG at the path asked for.
    @Test func screenshotOfTheWindowIsAPNGOfItsPixelSize() async throws {
        let (window, state) = paintedWindow()
        let path = FileManager.default.temporaryDirectory.appendingPathComponent("UIVerbs-\(UUID().uuidString)/window.png").path
        defer { try? FileManager.default.removeItem(atPath: (path as NSString).deletingLastPathComponent) }

        var intent = TakeScreenshotIntent()
        intent.path = path
        WindowState.front = state
        _ = try await intent.perform()

        let image = try png(at: path)
        let scale = window.backingScaleFactor
        #expect(image.pixelsWide == Int(320 * scale) && image.pixelsHigh == Int(200 * scale))
    }

    /// WHY: a picture of one pane must be THAT pane: the part of the window where the pane was laid out
    /// (top-left origin, as SwiftUI reports it), at its pixel size -- not the whole window, not a strip
    /// flipped from the bottom. And a pane that is not shown must refuse, naming the panes that are.
    @Test func screenshotOfAPaneIsThatPartOfTheWindow() throws {
        let (window, state) = paintedWindow()
        state.paneFrames[UIPane.library.frameKey] = CGRect(x: 20, y: 10, width: 100, height: 50)
        let dir = FileManager.default.temporaryDirectory.appendingPathComponent("UIVerbs-\(UUID().uuidString)")
        defer { try? FileManager.default.removeItem(at: dir) }
        let path = dir.appendingPathComponent("library.png").path

        let written = try UIVerbs.screenshot(of: .library, to: path, in: state)

        #expect(written == path)
        let image = try png(at: path)
        let scale = window.backingScaleFactor
        #expect(image.pixelsWide == Int(100 * scale) && image.pixelsHigh == Int(50 * scale))
        let middle = try #require(image.colorAt(x: image.pixelsWide / 2, y: image.pixelsHigh / 2)?.usingColorSpace(.sRGB))
        // Green, not the grey around it (a crop flipped from the bottom lands on grey).
        let isGreen = middle.greenComponent > middle.redComponent + 0.3 && middle.greenComponent > middle.blueComponent + 0.3
        #expect(isGreen, "the pane's own pixels: the green box, not \(middle)")

        let refusal = #expect(throws: FicheroUICapture.CaptureError.self) {
            try UIVerbs.screenshot(of: .preview, to: path, in: state)
        }
        guard case .paneNotShown(let name, let shown)? = refusal else {
            Issue.record("expected paneNotShown, got \(String(describing: refusal))")
            return
        }
        #expect(name == "preview" && shown == ["library"], "the refusal names the pane asked for and the panes shown")
    }
}
