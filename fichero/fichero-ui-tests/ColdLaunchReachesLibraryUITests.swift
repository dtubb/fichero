//
//  ColdLaunchReachesLibraryUITests.swift
//  FicheroUITests
//
//  The one launch test worth having: a cold embedded launch reaches the library
//  on its own, and never once offers the user a way to fix it.
//
//  The existing embedded smoke test asserts process liveness and that a window
//  exists — both of which stay TRUE through the exact bug Daniel hit. A window
//  showing "Can't Authenticate to Engine / Reset Sign-In" is still a window, and
//  the app is still running. That test would have gone green through the whole
//  incident, which is why this one asserts what actually went wrong.
//
//  WHY "no recovery button" IS the assertion, rather than "no gate":
//  BackendConnectionView legitimately renders during `.starting` — it IS the
//  booting splash, and a 23s cold engine means the user sees it. What must never
//  happen on a healthy launch is a FAILURE phase, and the recovery buttons are
//  exactly the thing that only renders in one (BackendConnectionView shows its
//  action row only when `showsFailureState` is true). So the buttons are the
//  precise signal, and the splash is not.
//
//  CANNOT RUN YET (#3902): no scheme references fichero-tests.xctestplan, and the
//  FicheroTests target carries a single build setting (PRODUCT_NAME) — no
//  SWIFT_VERSION, no INFOPLIST. Written now so it runs the moment that lands.
//
//  Also requires an EMBEDDED scheme: `--uitesting-embedded` exercises the real
//  bundled engine, which Debug does not embed (#3042).
//

import XCTest

final class ColdLaunchReachesLibraryUITests: XCTestCase {
    private var app: XCUIApplication!
    private var tempHome: URL!

    /// A cold engine is ~23.1s (import 9.6 + lifespan 13.5 + bind 0.5), and this
    /// test exists precisely because that is slower than people expect. Generous
    /// enough that a busy machine cannot make it flaky — the wait ends the moment
    /// the library appears, so the ceiling costs nothing on a healthy run.
    private let launchDeadline: TimeInterval = 120

    override func setUpWithError() throws {
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

    override func tearDownWithError() throws {
        app?.terminate()
        if let tempHome { try? FileManager.default.removeItem(at: tempHome) }
    }

    /// A healthy cold launch reaches the library with no user action, and never
    /// offers one.
    ///
    /// Polls rather than checking once at the end: a recovery button that appears
    /// and then resolves is still the bug — the user saw a dead end and clicked
    /// it. The end state alone cannot tell you that happened.
    @MainActor
    func testColdEmbeddedLaunchReachesLibraryWithoutEverOfferingRecovery() throws {
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
        let resetSignIn = app.buttons["backend.action.resetSignIn"]
        let restartEngine = app.buttons["backend.action.restartEngine"]

        let deadline = Date().addingTimeInterval(launchDeadline)
        while Date() < deadline {
            // A healthy launch never enters a failure phase, so neither recovery
            // action may EVER render — not even for one frame.
            XCTAssertFalse(
                resetSignIn.exists,
                "Reset Sign-In was offered during a healthy cold launch. There is no sign-in to "
                + "reset on an embedded engine, so the button appearing is itself the failure."
            )
            XCTAssertFalse(
                restartEngine.exists,
                "Restart Engine was offered during a healthy cold launch. The engine was starting "
                + "normally; the app gave up on it and asked the user to do its job."
            )

            if libraryContent.exists {
                return  // Reached the library, having never offered a way out.
            }
            Thread.sleep(forTimeInterval: 0.25)
        }

        XCTFail(
            "Cold embedded launch never reached library.content.ready within \(Int(launchDeadline))s, "
            + "without surfacing a recovery action either — the launch stalled silently."
        )
    }
}
