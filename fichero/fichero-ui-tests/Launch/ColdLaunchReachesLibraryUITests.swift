//
//  ColdLaunchReachesLibraryUITests.swift
//  FicheroUITests
//
//  The launch test that encodes the quality bar: a cold embedded launch reaches the
//  library on its own, and NEVER offers the user a way to fix it.
//
//  The existing embedded smoke test asserts process liveness and that a window
//  exists — both of which stay TRUE through the exact bug that shipped. A window
//  showing "Can't Authenticate to Engine / Reset Sign-In" is still a window, and
//  the app is still running. That test slept through the whole incident.
//
//  Requires an EMBEDDED scheme: `--uitesting-embedded` exercises the real bundled
//  engine, which Debug does not embed (#3042).
//

import XCTest

// @MainActor on the CLASS: XCUIApplication and friends are main-actor in the
// macOS 26 SDK, and XCTest runs actor-isolated test classes on their actor -
// this isolates setUp/tearDown/tests together with no per-call bridging.
@MainActor
final class ColdLaunchReachesLibraryUITests: XCTestCase {
    private var app: XCUIApplication!
    private var tempHome: URL!

    /// Ceiling, not an expectation. The engine measures ~5.27s mean (0.48s
    /// spread) since #3920, and #3930 means a slow engine is no longer a gate —
    /// so this only has to be generous enough that a busy machine cannot make the
    /// test flaky. The wait ends the instant the library appears, so a healthy run
    /// never pays it.
    private let launchDeadline: TimeInterval = 120

    /// How long to keep watching AFTER the library appears.
    ///
    /// This is the heart of the test. The reported failure was library FIRST,
    /// then "Can't Authenticate to Engine" seconds later — the 5s heartbeat
    /// probing `/api/registry`, getting a 401, and flipping a ready session to
    /// `.authRejected`. A test that returns the moment `library.content.ready`
    /// appears would go green through precisely that. 15s covers at least two
    /// heartbeat ticks.
    private let settleWindow: TimeInterval = 15

    override func setUp() async throws {
        // #4238: FAIL FAST when this build cannot supply an embedded engine.
        // Not a skip — a skipped launch test means the shipping launch path
        // has no coverage. Without this the launch never becomes ready and the
        // poll loop snapshots the whole accessibility tree ~4x/sec for 120s,
        // which reached 56 GB and took the machine down.
        try RequiresEngine.requireEmbeddedEngine()

        continueAfterFailure = false

        tempHome = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-uitest-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempHome, withIntermediateDirectories: true)

        app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-embedded"]
        app.launchEnvironment = [
            "FICHERO_UITEST_HOME": tempHome.path,
            "FICHERO_ALL_FEATURES": "1"
        ]
    }

    override func tearDown() async throws {
        app?.terminate()
        if let tempHome { try? FileManager.default.removeItem(at: tempHome) }
    }

    /// A healthy cold launch reaches the library with no user action, never offers
    /// one, and does not sprout one afterwards.
    @MainActor
    func testColdEmbeddedLaunchReachesLibraryWithoutEverOfferingRecovery() throws {
        // This test spawns the REAL bundled engine, so it only runs on the
        // embedded UI leg (scripts/verify_embedded_launch.sh / the Dev Embedded
        // scheme set FICHERO_UITEST_EMBEDDED=1). Under the Dev Local verify_all
        // leg there is no bundled engine, so it skips cleanly and the fast gate
        // stays green — replacing the old blanket #3968 XCTSkip that hid it
        // everywhere. It runs (and must pass) on the embedded leg.
        // Gated by TEST PLAN, not a runtime env var (env vars do not reliably reach
        // the UI-test RUNNER process — every scheme/TEST_RUNNER_ attempt silently
        // skipped). This test spawns the REAL bundled engine, so it is listed in
        // fichero.xctestplan's `skippedTests` — the Dev Local verify_all leg
        // (-testPlan fichero) skips it and stays green. scripts/verify_embedded_launch.sh
        // runs it with -only-testing (which overrides skippedTests) against the real
        // embedded engine. Verified to PASS there (real run ~34s, reaches library,
        // no failure splash).
        app.launch()
        XCTAssertTrue(
            app.wait(for: .runningForeground, timeout: 30),
            "App did not reach the foreground — likely crashed on launch."
        )

        // Query by identifier across ANY element type: `library.content.ready`
        // sits on a container, and containers do not reliably surface as
        // `otherElements`.
        let libraryContent = app.descendants(matching: .any)
            .matching(identifier: "library.content.ready").firstMatch

        // Phase 1 — reach the library, sweeping for recovery UI between waits.
        // Swept rather than asserted once at the end: a prompt that appears and
        // then resolves is still the bug (the user saw a dead end and clicked
        // it), and an end-state check cannot see that it happened.
        //
        // MEMORY DISCIPLINE (#4238): the wait is `waitForExistence` in 5s
        // chunks, NOT a tight `.exists` poll. Every `.exists` on a fresh query
        // makes XCUITest serialise an accessibility snapshot ("Capturing
        // element debug description"); at 4 checks x 4Hz x 120s that reached
        // 56 GB when the app never became ready. waitForExistence blocks
        // inside XCUITest without re-snapshotting per poll, so the worst case
        // is now ~24 chunk boundaries x 3 sweep queries — bounded by
        // construction, not by the precondition guard being right.
        // The trade-off is real but acceptable: a recovery prompt flashing
        // shorter than one chunk can slip between sweeps (at 0.25s polling the
        // same held for sub-poll flashes); the settle phase below still
        // catches anything that persists.
        let deadline = Date().addingTimeInterval(launchDeadline)
        var reachedLibrary = false
        while Date() < deadline {
            if libraryContent.waitForExistence(timeout: 5) {
                reachedLibrary = true
                break
            }
            assertNoRecoveryUI(phase: "during startup")
        }

        XCTAssertTrue(
            reachedLibrary,
            "Cold embedded launch never reached library.content.ready within \(Int(launchDeadline))s, "
            + "and never surfaced a recovery action either — the launch stalled silently."
        )

        // Phase 2 — the launch is not over when the library appears. Keep watching
        // across the heartbeat: a ready session that flips to .authRejected raises
        // the gate OVER the library, which is what the user actually saw.
        // 2.5s spacing spans the 15s window in 6 sweeps — enough to straddle at
        // least two 5s heartbeat ticks, without per-frame snapshot cost.
        let settleDeadline = Date().addingTimeInterval(settleWindow)
        while Date() < settleDeadline {
            assertNoRecoveryUI(phase: "after the library appeared")
            XCTAssertTrue(
                libraryContent.exists,
                "The library disappeared after loading — the session was torn back down post-ready."
            )
            Thread.sleep(forTimeInterval: 2.5)
        }
    }

    /// The recovery UI must never render on a healthy launch, in any form.
    ///
    /// `backend.connection.title` is the load-bearing assertion: it renders iff
    /// `showsFailureState`, so it catches EVERY failure phase — including
    /// `.portConflict`, which offers "Stop It / Use the Existing Engine / Quit"
    /// and would slip past a check that only knows the two named buttons.
    /// The buttons are asserted too, because they are the specific bar: on an
    /// embedded engine there is no sign-in to reset and no engine for the user to
    /// restart, so either button appearing IS the failure.
    @MainActor
    private func assertNoRecoveryUI(phase: String, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertFalse(
            app.descendants(matching: .any).matching(identifier: "backend.connection.title").firstMatch.exists,
            "A failure screen appeared \(phase) on a healthy cold launch.",
            file: file,
            line: line
        )
        XCTAssertFalse(
            app.buttons["backend.action.resetSignIn"].exists,
            "Reset Sign-In was offered \(phase). There is no sign-in to reset on an embedded "
            + "engine, so the button appearing is itself the failure.",
            file: file,
            line: line
        )
        XCTAssertFalse(
            app.buttons["backend.action.restartEngine"].exists,
            "Restart Engine was offered \(phase). The engine starts and is managed by the app; "
            + "asking the user to restart it is the app giving up on its own job.",
            file: file,
            line: line
        )
    }
}
