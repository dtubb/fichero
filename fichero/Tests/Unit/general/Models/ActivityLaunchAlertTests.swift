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
    override static func canInit(with request: URLRequest) -> Bool { true }
    override static func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        let path = request.url?.path ?? ""
        Self.seen.append((request.httpMethod ?? "", path))
        let (status, json): (Int, String) = switch path {
        case "/api/activity/stopped-at-quit":
            (200, #"{"items":[{"id":"r1","kind":"run-a-recipe","name":"Run the recipe: Letters","subject":null,"#
                + #""started_at":null},{"id":"t1","kind":"thumbnail","name":"Make thumbnails","subject":null,"#
                + #""started_at":null}],"count":2}"#)
        case "/api/activity/stopped-at-quit/continue":
            (200, #"{"continued_ids":["r1","t1"],"count":2}"#)
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
        #expect(message.contains("and background work: 1 embeds, 2 thumbnails"))
        #expect(message.contains("New files in a synced folder"))
        #expect(!message.contains("Make thumbnails"), "no row per thumbnail")
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
}
