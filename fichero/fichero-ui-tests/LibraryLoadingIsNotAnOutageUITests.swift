//
//  LibraryLoadingIsNotAnOutageUITests.swift
//  FicheroUITests
//
//  #3937 shipped: on every cold launch the library's very first frame
//  accused a perfectly healthy engine of being down — "Backend Not Connected /
//  The Fichero backend is not responding. Make sure the server is running on port
//  8765" — because `DocumentStore.isConnected` starts false and only flips true
//  after a load SUCCEEDS. A store that had simply never been asked for data read
//  as an outage.
//
//  The existing smoke test slept through it: it asserts process liveness and that
//  a window exists, and both are true of a window telling you a lie.
//
//  This is the gate for that CLASS of bug, not the one instance: at no point
//  during a healthy launch may the library claim the engine is unreachable. The
//  engine here is real (`--uitesting-embedded`) and starts normally, so any
//  outage claim is false by construction.
//

import XCTest

// @MainActor on the CLASS: XCUIApplication and friends are main-actor in the
// macOS 26 SDK, and XCTest runs actor-isolated test classes on their actor -
// this isolates setUp/tearDown/tests together with no per-call bridging.
@MainActor
final class LibraryLoadingIsNotAnOutageUITests: XCTestCase {
    private var app: XCUIApplication!
    private var tempHome: URL!

    private let launchDeadline: TimeInterval = 120

    override func setUp() async throws {
        continueAfterFailure = false
        // #4238: same polling pathology as ColdLaunch — a missing embedded
        // engine means 120s of full-tree snapshots instead of a failure.
        try RequiresEngine.requireEmbeddedEngine()

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

    /// A library that is still loading is starting up, not offline — and must
    /// never say otherwise, at any point, on a healthy engine.
    ///
    /// Polled from launch rather than checked at the end, because the bug was a
    /// FIRST FRAME: the pane appeared the instant the gate flipped ready and
    /// disappeared as soon as the first load returned. Checking once at the end
    /// would see the settled library and call it green — which is precisely how
    /// this reached the user.
    @MainActor
    func testHealthyLaunchNeverClaimsTheEngineIsUnreachable() throws {
        app.launch()
        XCTAssertTrue(
            app.wait(for: .runningForeground, timeout: 30),
            "App did not reach the foreground — likely crashed on launch."
        )

        let libraryContent = app.descendants(matching: .any)
            .matching(identifier: "library.content.ready").firstMatch
        let outage = app.descendants(matching: .any)
            .matching(identifier: "library.outage").firstMatch

        // ONE event-driven wait on a compound query, not a poll loop (#4238).
        // The old loop checked `.exists` 4x/sec, and every check serialised an
        // accessibility snapshot — 56 GB when the app never became ready. This
        // fires the moment EITHER element renders, so a transient outage frame
        // is caught by XCUITest's own event handling rather than by hoping a
        // poll lands inside it, and a stalled launch costs nothing but time.
        let readyOrOutage = app.descendants(matching: .any).matching(
            NSPredicate(format: "identifier IN %@", ["library.content.ready", "library.outage"])
        ).firstMatch
        XCTAssertTrue(
            readyOrOutage.waitForExistence(timeout: launchDeadline),
            "Never reached library.content.ready within \(Int(launchDeadline))s — the launch "
            + "stalled without ever claiming an outage either."
        )
        XCTAssertFalse(
            outage.exists,
            "The library claimed the engine was unreachable during a healthy launch. The "
            + "engine was starting or already serving; a library that has not loaded yet is "
            + "startup, not an outage (#3937)."
        )
        XCTAssertTrue(libraryContent.exists)

        // The first load lands after the library mounts, so keep watching across
        // it: the false outage was a transient frame in exactly this window.
        // waitForExistence RETURNING here is the failure — event-driven, so it
        // catches an outage frame shorter than any poll interval could.
        XCTAssertFalse(
            outage.waitForExistence(timeout: 10),
            "The library claimed an outage AFTER mounting, on a healthy engine (#3937)."
        )
    }
}
