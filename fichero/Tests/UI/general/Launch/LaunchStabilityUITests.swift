//
//  LaunchStabilityUITests.swift
//  FicheroUITests
//
//  Catches "launches, reaches readiness, then dies seconds later" — the failure
//  class hit during the 2026-09-17 environment-injection work (app ran, then
//  crashed on a missing WorkflowExecutionObserver ~25–40s after a healthy start).
//
//  Distinct from ColdLaunchReachesLibraryUITests, which sweeps the SAME kind of
//  post-readiness window for a RECOVERY SCREEN (a session that flips to
//  `.authRejected` and shows "Can't Authenticate to Engine"). This test's failure
//  mode is the app going away ENTIRELY with no recovery UI to see — a SIGTRAP or
//  crash takes the whole window, so a suite that only checks for a recovery
//  screen would find nothing to assert against. This checks process liveness
//  directly instead.
//
//  Requires an EMBEDDED scheme: exercises the real bundled engine (#3042), same
//  precondition as every other Launch/ suite.
//

import XCTest

@MainActor
final class LaunchStabilityUITests: XCTestCase {
    private var app: XCUIApplication!
    private var tempHome: URL!

    /// Same ceiling as the other Launch/ suites — generous, not an expectation;
    /// the wait ends the instant readiness appears.
    private let readyTimeout: TimeInterval = 120

    /// How long to keep checking AFTER readiness. Cheap by construction: each
    /// check reads `app.state` (process liveness), never an accessibility
    /// snapshot — so this can poll on a short interval without the #4238
    /// memory blowup a `.exists`/`descendants` poll loop would risk.
    private let settleWindow: TimeInterval = 30
    private let pollInterval: TimeInterval = 2

    override func setUp() async throws {
        // #4238: fail fast when this build/scheme cannot supply an embedded
        // engine, rather than polling to a dead end.
        try RequiresEngine.requireEmbeddedEngine()
        continueAfterFailure = false
        tempHome = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-uitest-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempHome, withIntermediateDirectories: true)
    }

    override func tearDown() async throws {
        app?.terminate()
        if let tempHome { try? FileManager.default.removeItem(at: tempHome) }
    }

    /// Launch, wait for genuine readiness (via `LaunchReadiness`, never a
    /// sleep), then keep confirming the app is still in the foreground for a
    /// bounded settle window.
    func testAppSurvivesTheSettleWindowAfterReachingReadiness() throws {
        app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-embedded"]
        app.launchEnvironment = [
            "FICHERO_UITEST_HOME": tempHome.path,
            "FICHERO_ALL_FEATURES": "1"
        ]
        app.launch()

        LaunchReadiness.waitUntilReady(app, timeout: readyTimeout)

        var elapsed: TimeInterval = 0
        while elapsed < settleWindow {
            XCTAssertEqual(
                app.state, .runningForeground,
                "App was healthy \(Int(elapsed))s after reaching readiness, but is no longer "
                + "in the foreground (state \(app.state.rawValue)) — it launched, reached "
                + "readiness, then died within the \(Int(settleWindow))s settle window."
            )
            guard app.state == .runningForeground else { break }
            Thread.sleep(forTimeInterval: pollInterval)
            elapsed += pollInterval
        }

        XCTAssertEqual(
            app.state, .runningForeground,
            "App is not in the foreground after the full \(Int(settleWindow))s settle window "
            + "following readiness (final state \(app.state.rawValue))."
        )
    }
}
