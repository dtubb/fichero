//
//  ToolbarModeLaunchStressUITests.swift
//  FicheroUITests
//
//  Launch-STRESS + toolbar-mode regression guard for the #3163 duplicate
//  `.searchable` NSToolbar launch crash.
//
//  The crash: two `.searchable` modifiers reach one window's NSToolbar →
//  `NSToolbar already contains an item with identifier com.apple.SwiftUI.search.
//  Duplicate items not allowed.` ContentView owns a GLOBAL toolbar `.searchable`
//  (ToolbarSearchableModifier, #3037); the Workflows/Chains/Actions mode views
//  ALSO applied their own bare `.searchable`, and in a secondary split-pane copy
//  the two collide → crash at launch. Intermittent (render-timing dependent),
//  so a single launch rarely reproduces it — hence the LAUNCH STRESS.
//
//  Why LibrarySmokeUITests never caught it: it launches with plain `--uitesting`
//  which skips the embedded engine + real-library restore, so `isBackendRunning`
//  stays false, the workspace (ContentView) never mounts, and the mode views'
//  toolbars are never built. It also only exercises flow 1 (launch) — it never
//  navigates INTO the Workflows/Chains modes where the duplicate `.searchable`
//  lived. This test fixes both gaps:
//    - it drives into the Workflows sidebar mode (⌃⌘4) whose split panes register
//      the colliding toolbar search, and toggles the Chains tab (the crash log
//      showed Chains active), and
//    - it needs the workspace actually mounted, so it must run against a
//      reachable engine (the gated CI/manual run provides one; a seeded library
//      can be pointed at via FICHERO_UITEST_LIBRARY). Under `--uitesting` the
//      inert-host adoption connects to an external engine if one is up.
//
//  Expected: RED on the pre-fix bare `.searchable`, GREEN on the gated
//  conditionalSearchable fix. Per the toolbar-crash memory, only a launch-stress
//  run WITH the engine + a real-enough library proves this — compile-only and
//  the `--uitesting` smoke test structurally cannot.
//

import XCTest

final class ToolbarModeLaunchStressUITests: XCTestCase {
    /// How many times to launch. The crash is render-timing dependent, so a
    /// single launch is unreliable; 8 gives a strong chance to hit it pre-fix.
    private let launchCount = 8

    private var tempHome: URL!

    override func setUpWithError() throws {
        continueAfterFailure = false
        tempHome = FileManager.default.temporaryDirectory
            .appendingPathComponent("fichero-toolbar-stress-\(UUID().uuidString)", isDirectory: true)
        try FileManager.default.createDirectory(at: tempHome, withIntermediateDirectories: true)
    }

    override func tearDownWithError() throws {
        if let tempHome { try? FileManager.default.removeItem(at: tempHome) }
    }

    private func makeApp() -> XCUIApplication {
        let app = XCUIApplication()
        // `--uitesting` isolates the run (temp home, no move-to-Applications
        // prompt) and triggers inert-host adoption — which connects to an
        // external engine if one is up, so the workspace mounts and the mode
        // toolbars actually build (#3163). FICHERO_ALL_FEATURES unlocks the
        // Workflows/Automation/etc. sidebar modes that are gated off by default.
        app.launchArguments = ["--uitesting"]
        var env = [
            "FICHERO_UITEST_HOME": tempHome.path,
            "FICHERO_ALL_FEATURES": "1"
        ]
        // Optional seeded `.fichero` so the workspace opens straight to content
        // (mirrors the #1242 reading-surface flows). Absent, the empty global
        // library still mounts the workspace + sidebar modes.
        if let seed = ProcessInfo.processInfo.environment["FICHERO_UITEST_LIBRARY"],
           !seed.isEmpty {
            env["FICHERO_UITEST_LIBRARY"] = seed
        }
        app.launchEnvironment = env
        return app
    }

    /// Launch the app `launchCount` times; each launch, drive into the Workflows
    /// sidebar mode (its split panes build the `.searchable` toolbar items that
    /// duplicated ContentView's global one), toggle the Chains tab, and flip back
    /// to Library — each mode switch rebuilds the toolbar, another place the
    /// duplicate surfaced. Assert the app never leaves the foreground; a
    /// duplicate-identifier NSToolbar crash drops it out of `.runningForeground`.
    @MainActor
    func testLaunchStressWorkflowChainsToolbarNoCrash() throws {
        for iteration in 1...launchCount {
            let app = makeApp()
            app.launch()

            XCTAssertTrue(
                app.wait(for: .runningForeground, timeout: 30),
                "Launch \(iteration): app never reached the foreground — likely crashed on launch."
            )
            XCTAssertTrue(
                app.windows.firstMatch.waitForExistence(timeout: 15),
                "Launch \(iteration): no window appeared after launch."
            )

            // Enter Workflows mode (⌃⌘4). Its split panes register the toolbar
            // `.searchable` that collided with ContentView's global one (#3163).
            app.typeKey("4", modifierFlags: [.control, .command])
            assertStillForeground(app, iteration: iteration, step: "after ⌃⌘4 Workflows")

            // Toggle to the Chains tab (the crash log showed Chains active).
            // Best effort — the mode switch alone already builds the collision,
            // so a missing segment doesn't fail the test.
            let chainsTab = app.buttons["Chains"].firstMatch
            if chainsTab.waitForExistence(timeout: 5) {
                chainsTab.click()
                assertStillForeground(app, iteration: iteration, step: "after Chains tab")
            }

            // Flip back to Library (⌃⌘1) and to Workflows (⌃⌘4) once more — each
            // switch re-runs the toolbar rebuild the crash rode in on.
            app.typeKey("1", modifierFlags: [.control, .command])
            assertStillForeground(app, iteration: iteration, step: "after ⌃⌘1 Library")
            app.typeKey("4", modifierFlags: [.control, .command])
            assertStillForeground(app, iteration: iteration, step: "after second ⌃⌘4 Workflows")

            app.terminate()
        }
    }

    /// A duplicate `.searchable` NSToolbar crash fires synchronously during the
    /// toolbar rebuild triggered by the mode switch, so give the rebuild a beat
    /// to complete + any NSException to surface, then assert the app is still
    /// foregrounded (a crash flips it to `.notRunning`).
    private func assertStillForeground(
        _ app: XCUIApplication,
        iteration: Int,
        step: String
    ) {
        // Deliberate settle window for the async toolbar rebuild + crash-if-any.
        Thread.sleep(forTimeInterval: 1.5)
        XCTAssertEqual(
            app.state,
            .runningForeground,
            "Launch \(iteration): app left the foreground \(step) — a duplicate "
            + ".searchable NSToolbar crash (#3163)."
        )
    }
}
