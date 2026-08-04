@testable import Fichero
import Foundation
import Testing

/// WebContent processes die for reasons outside the app (memory pressure,
/// sandbox bootstrap races, GPU resets — empirically, even a minimal sandboxed
/// WKWebView host loses one during startup on macOS 26.3). Apple's contract is
/// `webViewWebContentProcessDidTerminate(_:)`: the app hears about it and owns
/// recovery. These tests pin the bounded-reload policy and, structurally, that
/// EVERY Fichero web surface implements the callback — a surface without it
/// shows a permanently blank pane after a renderer death.
struct WebContentProcessRecoveryTests {

    // MARK: - The bounded reload budget

    @Test("the first termination reloads")
    func firstTerminationReloads() {
        var state = WebContentProcessRecovery.State()
        #expect(WebContentProcessRecovery.shouldReload(&state, now: Date()))
        #expect(state.attempts == 1)
    }

    /// A renderer that dies the moment it relaunches is crash-looping; the
    /// budget converts an infinite reload storm into an honest failure.
    @Test("a crash loop exhausts the budget and stops reloading")
    func crashLoopExhaustsTheBudget() {
        var state = WebContentProcessRecovery.State()
        let start = Date()
        for attempt in 1...WebContentProcessRecovery.maxAttempts {
            #expect(
                WebContentProcessRecovery.shouldReload(
                    &state, now: start.addingTimeInterval(Double(attempt))
                ),
                "attempt \(attempt) is within budget"
            )
        }
        #expect(
            !WebContentProcessRecovery.shouldReload(
                &state,
                now: start.addingTimeInterval(Double(WebContentProcessRecovery.maxAttempts) + 1)
            ),
            "the attempt past the budget must NOT reload"
        )
    }

    /// Occasional kills far apart must always recover — the budget is per
    /// window, not per lifetime.
    @Test("a quiet period resets the budget")
    func quietPeriodResetsTheBudget() {
        var state = WebContentProcessRecovery.State()
        let start = Date()
        for attempt in 0...WebContentProcessRecovery.maxAttempts {
            _ = WebContentProcessRecovery.shouldReload(
                &state, now: start.addingTimeInterval(Double(attempt))
            )
        }
        #expect(state.attempts > WebContentProcessRecovery.maxAttempts)
        let afterQuiet = start.addingTimeInterval(
            Double(WebContentProcessRecovery.maxAttempts)
                + WebContentProcessRecovery.attemptWindow + 1
        )
        #expect(WebContentProcessRecovery.shouldReload(&state, now: afterQuiet))
        #expect(state.attempts == 1, "the budget restarted")
    }

    // MARK: - Structural: every web surface recovers

    private static func appSource(_ relativePath: String) throws -> String {
        let url = try AppSource.root().appendingPathComponent(relativePath)
        return try String(contentsOf: url, encoding: .utf8)
    }

    /// A `WKWebView` whose WebContent process died renders nothing until it is
    /// reloaded. Every surface hosting one must therefore implement the
    /// termination callback and route recovery through the shared bounded
    /// policy — not hand-roll its own retry loop.
    @Test("every web surface implements the termination callback via the shared policy")
    func everyWebSurfaceRecovers() throws {
        for surface in [
            "Views/Reader/Knowledge/DocumentKGWebPaneCoordinator+Recovery.swift",
            "Views/Components/FicheroWebView.swift",
            "Views/Preview/WebContentCanvas.swift"
        ] {
            let source = try Self.appSource(surface)
            #expect(
                source.contains("func webViewWebContentProcessDidTerminate("),
                Comment(rawValue: surface)
            )
            #expect(
                source.contains("WebContentProcessRecovery.shouldReload("),
                Comment(rawValue: surface)
            )
        }
    }

    /// The reader coordinators must reload through `loadIfNeeded` (clearing
    /// its dedupe keys), not through `webView.reload()` — after a process
    /// death `reload()` has no committed navigation to repeat for a custom-
    /// scheme load, while `loadIfNeeded` rebuilds the request from state.
    @Test("the reader recovers by re-driving its own load path")
    func readerRecoversThroughItsOwnLoadPath() throws {
        let source = try Self.appSource(
            "Views/Reader/Knowledge/DocumentKGWebPaneCoordinator+Recovery.swift"
        )
        let bodies = source.components(
            separatedBy: "func webViewWebContentProcessDidTerminate("
        ).dropFirst()
        #expect(bodies.count == 2, "one recovery body per platform coordinator")
        for body in bodies {
            #expect(body.contains("loadIfNeeded(webView)"))
            #expect(body.contains("lastLoadedDocumentId = nil"), "dedupe keys must be cleared")
        }
    }
}
