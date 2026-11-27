//
//  ActivityLaunchAlertTests.swift
//  FicheroTests
//
//  #6584 `activity.launch.nothing-starts-one-alert`: the one alert at launch; its default leaves everything paused.
//

@testable import Fichero
import Foundation
import Testing

/// The engine of one project with two rows the quit stopped (the shape of `GET /api/activity/stopped-at-quit`); every
/// request is recorded, so a test sees whether a Continue went out.
private final class StoppedAtQuitMockURLProtocol: URLProtocol {
    nonisolated(unsafe) static var seen: [(method: String, path: String)] = []
    /// One test's own items for the list route (the JSON objects, comma-joined); nil: the two rows below.
    nonisolated(unsafe) static var items: String?
    override static func canInit(with request: URLRequest) -> Bool { true }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url?.path ?? ""
        Self.seen.append((request.httpMethod ?? "", path))
        let (status, json): (Int, String) = switch path {
        case "/api/activity/stopped-at-quit":
            (200, #"{"items":["# + (Self.items ?? #"{"id":"r1","kind":"run-a-recipe","name":"Run the recipe: Letters","subject":null,"#
                + #""started_at":null},{"id":"t1","kind":"thumbnail","name":"Make thumbnails","subject":null,"#
                + #""started_at":null}"#) + #"],"count":2}"#)
        case "/api/activity/stopped-at-quit/continue":
            (200, #"{"continued_ids":["r1","t1"],"count":2}"#)
        case "/api/actions/invoke":
            (200, #"{"ok":true,"audit_id":"audit-1","changed_domains":["activity"],"#
                + #""result":{"deleted_ids":["r1","t1"],"skipped_ids":[],"count":2}}"#)
        default:
            (404, #"{"detail":"not stubbed"}"#)
        }
        let response = HTTPURLResponse(url: request.url!, statusCode: status, httpVersion: nil,
                                       headerFields: ["Content-Type": "application/json"])!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data(json.utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@MainActor
@Suite(.serialized)
struct ActivityLaunchAlertTests {
    private func project() -> LibraryManager.LibraryReference {
        StoppedAtQuitMockURLProtocol.seen = []
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [StoppedAtQuitMockURLProtocol.self]
        return LibraryManager.LibraryReference(
            url: URL(fileURLWithPath: "/tmp/ActivityLaunchAlertTests.fichero"), document: FicheroDocument(),
            displayName: "Letters", session: URLSession(configuration: configuration))
    }

    @Test("the title counts, the message names at most five and says nothing runs")
    func titleAndMessage() {
        #expect(StoppedAtQuitAlert.title(count: 1) == "1 run was stopped when Fichero quit")
        #expect(StoppedAtQuitAlert.title(count: 3) == "3 runs were stopped when Fichero quit")
        #expect(StoppedAtQuitAlert.title(count: 0) == "Background work was stopped when Fichero quit", "never \"0 runs\"")
        let message = StoppedAtQuitAlert.message(names: ["Run the recipe: Letters", "Make thumbnails"])
        #expect(message.hasPrefix("Run the recipe: Letters\nMake thumbnails\n"))
        #expect(message.contains("Nothing runs until you choose"))
        let many = StoppedAtQuitAlert.message(names: (1...7).map { "Run \($0)" })
        #expect(many.contains("and 2 more"))
        #expect(!many.contains("Run 6"))
    }

    @Test("automatic work rolls into one line and a held folder read into another; the title counts the runs alone")
    func rollups() {
        let message = StoppedAtQuitAlert.message(items: [
            ("Run the recipe: Letters", "run-a-recipe"),
            ("Make thumbnails", "thumbnail"), ("Make thumbnails", "thumbnail"), ("Embed for search", "embedding"),
            ("Read a synced folder", "read-from-folder")
        ])
        #expect(message.hasPrefix("Run the recipe: Letters\n"))
        #expect(message.contains("and background work: 1 embed, 2 thumbnails"), "plural by count, never 1 embeds")
        #expect(message.contains("New files in a synced folder"))
        #expect(!message.contains("Make thumbnails"), "no row per thumbnail")
        let alone = StoppedAtQuitAlert.message(items: [("Embed for search", "embed"), ("Make thumbnails", "thumbnail")])
        #expect(alone.hasPrefix("Background work: 1 embed, 1 thumbnail\n"), "no \"and\" with no run before it")
    }

    @Test("a held folder read is named by its folder, one line per folder; one with no name keeps the plain line")
    func newMaterialNamesItsFolder() {
        let reads = [("Read a synced folder", "read-from-folder"), ("Read a synced folder", "read-from-folder")]
        let named = StoppedAtQuitAlert.message(items: reads, folders: ["inbox", "scans"])
        #expect(named.hasPrefix("New files in inbox\nNew files in scans\n"))
        #expect(!named.contains("synced folder"))
        let one = StoppedAtQuitAlert.message(items: reads, folders: ["inbox"])
        #expect(one.hasPrefix("New files in inbox\nNew files in a synced folder\n"))
    }

    @Test("the alert reads the folder's name from the engine's item")
    func theFolderComesFromTheEngine() async {
        let library = project()
        StoppedAtQuitMockURLProtocol.items = #"{"id":"f1","kind":"read-from-folder","name":"Read a synced folder","#
            + #""subject":"f-inbox","started_at":null,"folder":"inbox"}"#
        defer { StoppedAtQuitMockURLProtocol.items = nil }
        let alert = StoppedAtQuitAlert()
        await alert.check(libraries: [library])
        #expect(alert.items.map(\.folder) == ["inbox"])
        #expect(alert.message.hasPrefix("New files in inbox\n"))
    }

    @Test("with nothing stopped the alert never shows")
    func nothingStoppedShowsNothing() async {
        let alert = StoppedAtQuitAlert()
        await alert.check(libraries: [])
        #expect(!alert.isPresented)
    }

    @Test("Leave Paused, the default, dismisses and sends nothing: the held rows stay paused in the engine")
    func leavePausedIsTheDefault() async {
        let library = project()
        let alert = StoppedAtQuitAlert()
        await alert.check(libraries: [library])
        #expect(alert.isPresented)
        #expect(alert.items.map(\.jobId) == ["r1", "t1"])

        alert.leavePaused()

        #expect(!alert.isPresented && alert.items.isEmpty)
        #expect(StoppedAtQuitMockURLProtocol.seen.map(\.path) == ["/api/activity/stopped-at-quit"],
                "only the read went out: no Continue, so nothing the quit stopped is let go")
        #expect(!StoppedAtQuitMockURLProtocol.seen.contains { $0.method == "POST" })
    }

    @Test("Continue All is the one way the held rows are let go")
    func continueAllSendsTheContinue() async {
        let library = project()
        let alert = StoppedAtQuitAlert()
        await alert.check(libraries: [library])
        await alert.continueAll(libraries: [library])
        #expect(StoppedAtQuitMockURLProtocol.seen.contains {
            $0.method == "POST" && $0.path == "/api/activity/stopped-at-quit/continue"
        })
        #expect(!alert.isPresented)
    }

    @Test("four answers in order, Leave Paused first and Delete All destructive; SwiftUI's Mac alert dropped the fourth")
    func fourAnswers() {
        #expect(StoppedAtQuitAlert.Choice.allCases.map(\.title) == ["Leave Paused", "Choose…", "Continue All", "Delete All"])
        #expect(StoppedAtQuitAlert.Choice.allCases.filter(\.isDestructive) == [.deleteAll])
    }

    @Test("Choose… opens Activity and sends nothing: the rows stay paused there for the person to pick from")
    func chooseOpensActivity() async {
        let library = project()
        let alert = StoppedAtQuitAlert()
        await alert.check(libraries: [library])
        var opened: [ActivitySelection] = []
        await alert.answer(.choose, libraries: [library], steps: nil) { opened = $0 }
        #expect(opened.map(\.jobId) == ["r1", "t1"] && opened.allSatisfy { $0.libraryId == library.id },
                "Activity opens with the stopped rows selected")
        #expect(!alert.isPresented)
        #expect(!StoppedAtQuitMockURLProtocol.seen.contains { $0.method == "POST" })
    }

    @Test("Delete All is one step on the front window's stack, though the alert sits above the window's environment")
    func deleteAllIsUndoable() async {
        let library = project()
        let alert = StoppedAtQuitAlert()
        await alert.check(libraries: [library])
        let saved = WindowState.front
        let window = WindowState(libraryId: library.id)
        window.steps.engineForProject = { _ in nil }  // the step's own service
        WindowState.front = window
        defer { WindowState.front = saved }

        await alert.answer(.deleteAll, libraries: [library], steps: nil) { _ in }

        #expect(StoppedAtQuitMockURLProtocol.seen.contains { $0.method == "POST" && $0.path == "/api/actions/invoke" })
        #expect(window.steps.canUndo && window.steps.undoName == "Delete 2 Rows", "Edit › Undo puts them back")
        #expect(!alert.isPresented)
    }
}
