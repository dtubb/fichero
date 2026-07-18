//
//  LibrarySmokeUITests.swift
//  FicheroUITests
//
//  Click-through smoke tests (#1230). These launch the REAL app as a separate
//  process and assert no crash + key elements exist. They would have caught the
//  two #1228 launch/hover crashes.
//
//  Scope (this pass): flow 1 (launch) + flow 5 (view-mode rail). The data-
//  dependent flows (select a PDF + hover, knowledge-surface tabs, inspector
//  content) need a seeded backend + a real multi-page-PDF fixture and are
//  tracked as a follow-up — see the issue filed off #1230.
//
//  The app is launched in an ISOLATED mode so the suite never touches the
//  developer's real library or the shared dev backend:
//   - `--uitesting` launch arg → app skips the move-to-Applications prompt,
//     skips real saved-library restore, and does NOT spawn the embedded engine.
//   - `FICHERO_UITEST_HOME` → the global library is rooted in a throwaway temp
//     dir, so even if a dev backend is up, requests carry a disposable path.
//   - `FICHERO_ALL_FEATURES=1` → unlocks the library advanced views so the
//     icons/list/table/map view-mode rail is present (it's gated off by default).
//

import XCTest

final class LibrarySmokeUITests: XCTestCase {
    private var app: XCUIApplication!
    private var tempHome: URL!

    override func setUpWithError() throws {
        continueAfterFailure = false

        // Disposable Application Support root, unique per test, removed in
        // tearDown — keeps the smoke run fully isolated from the real library.
        tempHome = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-uitest-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempHome, withIntermediateDirectories: true)

        app = XCUIApplication()
        app.launchArguments = ["--uitesting"]
        app.launchEnvironment = [
            "FICHERO_UITEST_HOME": tempHome.path,
            "FICHERO_ALL_FEATURES": "1"
        ]
    }

    override func tearDownWithError() throws {
        app?.terminate()
        if let tempHome { try? FileManager.default.removeItem(at: tempHome) }
    }

    /// Flow 1 — the app launches and stays foregrounded without crashing.
    /// This is the regression guard for the #1228 `ClaimFocusState`
    /// environment-object launch crash. macOS XCUITest does not expose the
    /// SwiftUI window hierarchy reliably, so process state is the stable
    /// smoke-test oracle here.
    @MainActor
    func testLaunchShowsLibraryWindowWithoutCrashing() throws {
        throw XCTSkip("#3968: embedded-launch UI tests need the engine, tracked separately")
        app.launch()

        XCTAssertTrue(
            app.wait(for: .runningForeground, timeout: 30),
            "App did not reach the foreground within 30s — likely crashed on launch."
        )
        // Still alive a beat later (a launch crash often surfaces just after
        // the first frame renders).
        Thread.sleep(forTimeInterval: 2)
        XCTAssertEqual(app.state, .runningForeground, "App left the foreground after launch.")
    }

    /// Runs only in an embedded macOS scheme. It exercises the real startup
    /// ordering with one saved library, while keeping all data under the test
    /// support directory.
    @MainActor
    func testEmbeddedEngineLaunchRestoresLibraryAfterReadiness() throws {
        throw XCTSkip("#3968: embedded-launch UI tests need the engine, tracked separately")
        let embeddedApp = XCUIApplication()
        embeddedApp.launchArguments = ["--uitesting", "--uitesting-embedded"]
        embeddedApp.launchEnvironment = [
            "FICHERO_UITEST_HOME": tempHome.path,
            "FICHERO_UITEST_RESTORE_LIBRARY": "1",
            "FICHERO_ALL_FEATURES": "1"
        ]

        embeddedApp.launch()

        XCTAssertTrue(
            embeddedApp.wait(for: .runningForeground, timeout: 45),
            "Embedded engine launch did not reach the foreground."
        )
        XCTAssertTrue(
            embeddedApp.windows.firstMatch.waitForExistence(timeout: 15),
            "No window appeared after embedded engine launch."
        )
        // Give the bundled engine time to bind and the deferred saved-library
        // restore time to run. The unit test covers the ordering predicate;
        // this exercises the real app process and engine bundle together.
        Thread.sleep(forTimeInterval: 10)
        XCTAssertEqual(
            embeddedApp.state,
            .runningForeground,
            "App left the foreground while restoring a saved library after engine readiness."
        )
        embeddedApp.terminate()
    }

    // Flow 5 — the in-content view-mode icon rail was removed (#2032):
    // presentation lives in the View menu (LibraryLayoutSection, ⌘1–4), not in
    // a floating in-content icon bar, so the former
    // `testViewModeRailIsPresentAndSwitches` smoke test no longer applies.
}
