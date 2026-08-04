//
//  FicheroUISession.swift
//  FicheroUITests
//
//  Shared-session base for functional UI tests (#4246): ONE engine, ONE seeded
//  library, ONE app launch per test RUN — every functional suite drives that
//  same app instance.
//
//  Rationale (encode once, here): launching the app is the most expensive and
//  flakiest operation a UI test performs, so the run pays it exactly once.
//  Per-test isolation comes from resetting STATE inside the running app, not
//  from relaunching it. The only exception is the launch-path suites
//  (ColdLaunch / LaunchPerformance / LibraryLoadingIsNotAnOutage), where the
//  launch itself is the behaviour under test — the same layering WebKit uses:
//  a thin ring of launch tests around a body of shared-session tests. The
//  per-test / per-launch spawn patterns this replaces were the crash class:
//  plan storms multiplied engine boots until the machine went down.
//
//  What the session provisions (class-scoped, shared across ALL subclasses —
//  statics live on this base class, so the whole run shares one of each):
//   - UITestEngineHarness: a disposable UDS engine over a freshly seeded
//     library (the same Python seeder the contract walker uses),
//   - one XCUIApplication launched with FICHERO_FORCE_UDS_PATH,
//     FICHERO_UITEST_HOME and FICHERO_UITEST_LIBRARY, so the app under test
//     opens the seeded library over the private socket and never touches the
//     developer's real data.
//
//  Per-test isolation: `resetToKnownState()` runs in setUp. First version is
//  keyboard/menu navigation — dismiss any transient UI, return to the Library
//  sidebar mode, clear the selection. FOLLOW-UP (tracked in #4246): an
//  app-side test-only reset hook — e.g. a FICHERO_UITEST_RESET command over a
//  local channel or a URL-scheme route, compiled in only behind --uitesting —
//  would make resets millisecond-cheap and exact; keyboard navigation is the
//  bootstrap version, not the destination.
//
//  Evidence trail: every session test that fails attaches a screenshot of the
//  app at failure time (XCUIScreen snapshot, kept always) — cheap, and turns
//  "the wait timed out" into something a human can diagnose.
//

import XCTest

// @MainActor on the CLASS: XCUIApplication and friends are main-actor in the
// macOS 26 SDK, and XCTest runs actor-isolated test classes on their actor.
@MainActor
class FicheroUISessionTests: XCTestCase {
    // Session state, shared across every subclass in the run. The engine is
    // torn down by the harness's atexit + FICHERO_PARENT_PID backstops when
    // the test RUNNER process exits (a class-level tearDown cannot know it is
    // the last session class, so nothing tears down mid-run).
    // `nonisolated(unsafe)`: statics on a @MainActor class are actor-isolated
    // and XCTest executes tests serially — never concurrently.
    nonisolated(unsafe) private static var sharedHarness: UITestEngineHarness?
    nonisolated(unsafe) private static var sharedSeeded: UITestEngineHarness.SeededLibrary?
    nonisolated(unsafe) private static var sharedApp: XCUIApplication?
    nonisolated(unsafe) private static var provisioningError: Error?

    /// The seeded fixture the session serves.
    private(set) var seeded: UITestEngineHarness.SeededLibrary!
    /// The single app instance every session test drives.
    private(set) var app: XCUIApplication!

    /// The seeded document that carries entities (fixed id in the seeder).
    var letterDocumentId: String { seeded.ids["doc_letter"] ?? "test-doc-letter" }

    /// Generous ceiling for engine cold import + the app reaching the library
    /// over UDS. Waits end the instant the target appears.
    let readyTimeout: TimeInterval = 120

    override func setUp() async throws {
        continueAfterFailure = false

        if Self.sharedHarness == nil, Self.provisioningError == nil {
            let harness = UITestEngineHarness()
            do {
                Self.sharedSeeded = try harness.start()
                Self.sharedHarness = harness
            } catch {
                Self.provisioningError = error
            }
        }
        if let error = Self.provisioningError {
            // No venv / seeder / repo on this machine — skip rather than red.
            throw XCTSkip("Could not provision the UI-test session engine: \(error)")
        }
        seeded = Self.sharedSeeded

        // Launch-owning suites (the fichero-embedded plan) terminate/relaunch
        // the app under test; if one interleaves with session suites — or a
        // prior session test crashed the app and already failed for it — the
        // shared instance may be gone. Re-provision rather than cascade
        // failures into unrelated tests.
        if let existing = Self.sharedApp, existing.state != .runningForeground {
            Self.sharedApp = nil
        }
        if Self.sharedApp == nil {
            let newApp = XCUIApplication()
            newApp.launchArguments = ["--uitesting"]
            newApp.launchEnvironment = [
                // Inert host + UDS override → the app dials the session engine
                // over the private socket (no TCP, no TLS, no token).
                "FICHERO_FORCE_UDS_PATH": seeded.socketPath,
                "FICHERO_UITEST_HOME": seeded.appHomePath,
                "FICHERO_UITEST_LIBRARY": seeded.libraryPath,
                // Open the entity-bearing seeded document into the detail pane
                // at launch, so document-scoped suites have their subject ready.
                "FICHERO_UITEST_OPEN_DOCUMENT": seeded.ids["doc_letter"] ?? "test-doc-letter",
                // Unlock gated surfaces (knowledge inspector, advanced views).
                "FICHERO_ALL_FEATURES": "1"
            ]
            newApp.launch()
            Self.sharedApp = newApp
        }
        app = Self.sharedApp

        // A crash mid-test is caught (and failed) by the test that caused it;
        // this only confirms the session instance is usable for THIS test.
        XCTAssertEqual(
            app.state, .runningForeground,
            "The shared session app is not foregrounded even after (re)launch."
        )

        resetToKnownState()
    }

    override func tearDown() async throws {
        // Evidence on failure: attach what the app looked like when it failed.
        if let run = testRun, run.totalFailureCount > 0, let app = Self.sharedApp,
           app.state == .runningForeground {
            let shot = XCUIScreen.main.screenshot()
            let attachment = XCTAttachment(screenshot: shot)
            attachment.name = "failure-\(name)"
            attachment.lifetime = .keepAlways
            add(attachment)
        }
        // Deliberately NOT terminating the app: the session outlives the test.
    }

    // MARK: - Per-test reset (v1: keyboard/menu navigation)

    /// Return the running app to a known baseline: no transient UI, Library
    /// sidebar mode. Bootstrap version — see the header for the planned
    /// app-side reset hook that replaces this with an exact millisecond reset.
    func resetToKnownState() {
        guard app.state == .runningForeground else { return }
        // Dismiss any popover/sheet/menu a previous test left open.
        app.typeKey(.escape, modifierFlags: [])
        app.typeKey(.escape, modifierFlags: [])
        // Back to the Library sidebar mode (⌃⌘1 — the mode shortcuts).
        app.typeKey("1", modifierFlags: [.control, .command])
    }

    // MARK: - Shared oracles

    /// Block until the library content is ready (the cold-launch oracle).
    /// `library.content.ready` sits on a container, so query ANY type.
    func waitForLibraryReady(
        file: StaticString = #filePath, line: UInt = #line
    ) {
        let ready = app.descendants(matching: .any)
            .matching(identifier: "library.content.ready").firstMatch
        XCTAssertTrue(
            ready.waitForExistence(timeout: readyTimeout),
            "Library never reached `library.content.ready` within \(Int(readyTimeout))s — "
            + "the app never connected to the session's seeded UDS engine.",
            file: file, line: line
        )
    }
}
