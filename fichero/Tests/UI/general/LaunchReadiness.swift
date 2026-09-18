//
//  LaunchReadiness.swift
//  FicheroUITests
//
//  Reusable launch-readiness wait: "launched" (process foregrounded, a window
//  exists) is NOT the same as "ready to drive". On macOS the app spawns its own
//  bundled engine at launch and does not become interactable until that engine
//  answers ready — `library.content.ready`, published by BackendRootGate only
//  once the seeded/real library is actually on screen. Every UI test that
//  launches (or relaunches) the app should wait through THIS helper, never a
//  fixed `sleep()`: a sleep either wastes time on a healthy run, or is too short
//  on a loaded machine and lets the test start asserting against a window that
//  has not finished booting — the exact race the maintainer flagged.
//

import XCTest

enum LaunchReadiness {

    /// Bounded wait for a genuine readiness signal — a queryable, existing
    /// element — never a fixed sleep. Uses `waitForExistence`, which blocks
    /// inside XCUITest without re-snapshotting the accessibility tree per poll
    /// (unlike a tight `.exists` loop; see #4238 in RequiresEngine.swift for why
    /// that distinction matters). Fails with a diagnostic message naming what it
    /// waited for and how long, so a failure reads as "the app never reached
    /// readiness" rather than a bare "element not found".
    ///
    /// Queries `matching(identifier:)` across ANY element type, not just
    /// `.otherElements`: the readiness anchor sits on a container that does not
    /// reliably surface as one accessibility role.
    @MainActor
    @discardableResult
    static func waitUntilReady(
        _ app: XCUIApplication,
        identifier: String = "library.content.ready",
        timeout: TimeInterval = 120,
        file: StaticString = #filePath,
        line: UInt = #line
    ) -> Bool {
        let anchor = app.descendants(matching: .any).matching(identifier: identifier).firstMatch
        let ready = anchor.waitForExistence(timeout: timeout)
        XCTAssertTrue(
            ready,
            "App never reached readiness: waited \(Int(timeout))s for an element with "
            + "accessibility identifier \"\(identifier)\" to exist. Launch finished (the "
            + "process foregrounded) but the app never signalled it was ready to drive — "
            + "it spawns its own bundled engine at launch and waits for it, so "
            + "\"launched\" is not \"ready\". If this fires on a healthy machine, the "
            + "readiness anchor itself may have moved or the engine never came up.",
            file: file, line: line
        )
        return ready
    }
}
