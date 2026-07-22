//
//  LaunchPerformanceUITests.swift
//  FicheroUITests
//
//  Launch time as a TRACKED NUMBER, not a log line someone has to read.
//
//  #3946 put the launch on a timeline and emitted it as os_signpost intervals.
//  This turns those intervals into XCTest metrics, so a regression is a failing
//  test rather than something you notice months later.
//
//  The two metrics answer different questions, which is the point of having both:
//
//    • XCTApplicationLaunchMetric — the SYSTEM's launch: process start to first
//      frame. The front-end half. Owned by us: dyld, static init, SwiftUI.
//    • XCTOSSignpostMetric("launch") — OUR interval: AppState.init to the
//      library actually being on screen. Includes waiting for the engine.
//    • XCTOSSignpostMetric("engine startup wait") — the engine's contribution
//      alone, so a front-end regression can never hide behind a slow engine, and
//      an engine regression cannot be blamed on the app.
//
//  RUNNING vs GATING: these run and report with no scheme change. They do NOT
//  fail on regression until a baseline is recorded per-device in Xcode (Product ▸
//  Test, then set the baseline from the result). Without a baseline `measure`
//  reports the numbers and always passes — which is still useful, and is the
//  honest starting point given the engine's own spread (0.48s).
//

import XCTest

final class LaunchPerformanceUITests: XCTestCase {
    /// Must match `LaunchProfile.signposter`'s subsystem.
    private static let subsystem = "app.fichero.fichero"
    /// `OSLog.Category.pointsOfInterest` serialises to this. It is why the
    /// signposts need no Instruments configuration, and it is what this metric
    /// has to name to find them.
    private static let category = "PointsOfInterest"

    private var tempHome: URL!

    override func setUpWithError() throws {
        continueAfterFailure = false
        tempHome = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-uitest-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempHome, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        if let tempHome { try? FileManager.default.removeItem(at: tempHome) }
    }

    private func makeApp() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-embedded"]
        app.launchEnvironment = [
            "FICHERO_UITEST_HOME": tempHome.path,
            "FICHERO_ALL_FEATURES": "1"
        ]
        return app
    }

    /// Launch, measured end to end.
    ///
    /// The block waits for the library rather than returning at `launch()`,
    /// because our "launch" interval does not close until ContentView's first
    /// frame — a block that returned early would end before the interval did and
    /// leave the signpost metric nothing to measure.
    ///
    /// Each iteration spawns a REAL engine, so this is a slow test by
    /// construction (~5.27s of engine per iteration, plus the port pre-flight
    /// sweeping the previous iteration's engine off :8765). That cost is the
    /// thing being measured; making it cheap would make it fiction.
    @MainActor
    func testColdLaunchPerformance() throws {
        let metrics: [XCTMetric] = [
            XCTApplicationLaunchMetric(),
            XCTOSSignpostMetric(subsystem: Self.subsystem, category: Self.category, name: "launch"),
            XCTOSSignpostMetric(
                subsystem: Self.subsystem,
                category: Self.category,
                name: "engine startup wait"
            )
        ]

        let options = XCTMeasureOptions()
        // Each iteration is a full engine cold start; five of those is minutes.
        // Three still separates a real regression from the engine's 0.48s spread.
        options.iterationCount = 3

        measure(metrics: metrics, options: options) {
            let app = makeApp()
            app.launch()
            let libraryContent = app.descendants(matching: .any)
                .matching(identifier: "library.content.ready").firstMatch
            XCTAssertTrue(
                libraryContent.waitForExistence(timeout: 120),
                "Launch never reached the library, so this iteration measured a failure, not a launch."
            )
            // Terminate inside the block so the engine is gone before the next
            // iteration's port pre-flight, rather than being swept by it.
            app.terminate()
        }
    }
}
