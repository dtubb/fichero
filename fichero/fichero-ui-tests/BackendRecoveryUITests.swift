//
//  BackendRecoveryUITests.swift
//  FicheroUITests
//
//  #3919 — the backend recovery UI carried no accessibility identifiers, so
//  nothing could assert on it. These launch the REAL app with nothing to talk
//  to: `--uitesting` selects the `.inert` provisioning strategy, which never
//  spawns the embedded engine, so the root gate parks on a NON-AUTH failure
//  (`.unreachable`, remedy `.restartEngine`).
//
//  The invariant under test is #3919's: a failure that is not an authentication
//  failure must offer its own recovery and must NOT offer "Reset Sign-In".
//  On an embedded loopback engine there is no sign-in to reset, so that button
//  appearing is itself the failure.
//

import XCTest

final class BackendRecoveryUITests: XCTestCase {
    private var app: XCUIApplication!
    private var tempHome: URL!

    override func setUpWithError() throws {
        continueAfterFailure = false

        // Disposable Application Support root, removed in tearDown — keeps the
        // run isolated from the developer's real library (same pattern as
        // LibrarySmokeUITests).
        tempHome = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-uitest-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempHome, withIntermediateDirectories: true)

        app = XCUIApplication()
        app.launchArguments = ["--uitesting"]
        app.launchEnvironment = ["FICHERO_UITEST_HOME": tempHome.path]
    }

    override func tearDownWithError() throws {
        app?.terminate()
        if let tempHome { try? FileManager.default.removeItem(at: tempHome) }
    }

    /// A non-auth engine failure offers its own recovery and never the sign-in
    /// remedy (#3919).
    @MainActor
    func testNonAuthFailureOffersRecoveryWithoutResetSignIn() throws {
        app.launch()
        XCTAssertTrue(
            app.wait(for: .runningForeground, timeout: 30),
            "App did not reach the foreground — likely crashed on launch."
        )

        // `AppState.checkBackendHealthUntilReady` re-probes with backoff
        // (1,2,3,4,5,5s ≈ 20s) before parking on `.unreachable`. While it
        // re-probes, the phase returns to `.starting` and the failure UI is
        // replaced by the booting splash. Wait the loop out so the assertions
        // below run against a SETTLED failure rather than a flicker — an absence
        // check taken during the splash would pass vacuously. Once the loop
        // ends the heartbeat keeps polling but never re-enters `.starting`, so
        // the phase is stable from here.
        Thread.sleep(forTimeInterval: 30)

        let failureTitle = app.staticTexts["backend.connection.title"]
        XCTAssertTrue(
            failureTitle.waitForExistence(timeout: 30),
            "The connection view never settled on a failure state with no engine running."
        )

        // There must be an actionable next step — never a blank box.
        XCTAssertTrue(
            app.buttons["backend.action.restartEngine"].exists,
            "A non-auth failure must still offer a recovery action."
        )

        // ...and it must not be the sign-in remedy. Nothing here is a rejected
        // credential, so "Reset Sign-In" would misdiagnose the failure and
        // offer to clear a token that was never the problem.
        XCTAssertFalse(
            app.buttons["backend.action.resetSignIn"].exists,
            "Reset Sign-In must not be offered for a non-authentication failure (#3919)."
        )
    }
}
