//
//  ToolbarModeLaunchStressUITests.swift
//  FicheroUITests
//
//  Toolbar-mode regression guard for the #3163 duplicate `.searchable`
//  NSToolbar crash.
//
//  The crash: two `.searchable` modifiers reach one window's NSToolbar →
//  `NSToolbar already contains an item with identifier com.apple.SwiftUI.search.
//  Duplicate items not allowed.` ContentView owns a GLOBAL toolbar `.searchable`
//  (ToolbarSearchableModifier, #3037); the Workflows/Chains/Actions mode views
//  ALSO applied their own bare `.searchable`, and in a secondary split-pane copy
//  the two collide → crash. Intermittent (render-timing dependent), so the test
//  cycles the toolbar rebuild many times.
//
//  Session conversion (#4246): this suite previously paid THREE embedded-engine
//  launches (eight under the stress flag) for a crash that lives entirely in the
//  UI layer — the collision fires during the NSToolbar REBUILD a sidebar-mode
//  switch triggers, not during process launch. The workspace merely has to be
//  mounted (a connected engine), which the shared session already provides. So:
//  one shared launch, and the stress budget goes into mode-switch CYCLES, each
//  of which rebuilds the toolbar exactly like the launch-time rebuild did. The
//  multi-launch bought only first-frame timing variance, at the cost of three
//  engine boots — if a regression ever reproduces exclusively on a fresh
//  launch's first toolbar build, the embedded launch suites (ColdLaunch et al.)
//  are the place for it, not a multi-launch loop here.
//

import XCTest

@MainActor
final class ToolbarModeLaunchStressUITests: FicheroUISessionTests {
    /// The crash is render-timing dependent, so cycle the rebuild repeatedly.
    /// Mode switches are cheap against the shared session (~seconds), so the
    /// default budget is higher than the old 3-launch pass; CI can request the
    /// longer stress pass with FICHERO_RUN_LAUNCH_STRESS=1.
    private var cycleCount: Int {
        ProcessInfo.processInfo.environment["FICHERO_RUN_LAUNCH_STRESS"] == "1" ? 24 : 6
    }

    /// Drive into the Workflows sidebar mode (its split panes register the
    /// toolbar `.searchable` that collided with ContentView's global one),
    /// toggle the Chains tab (the crash log showed Chains active), and flip
    /// back to Library — each mode switch rebuilds the toolbar, which is where
    /// the duplicate surfaced. Assert the app never leaves the foreground; a
    /// duplicate-identifier NSToolbar crash drops it out of `.runningForeground`.
    @MainActor
    func testModeCycleWorkflowChainsToolbarNoCrash() throws {
        waitForLibraryReady()

        for iteration in 1...cycleCount {
            // Enter Workflows mode (⌃⌘4) — builds the colliding toolbar items.
            app.typeKey("4", modifierFlags: [.control, .command])
            assertStillForeground(iteration: iteration, step: "after ⌃⌘4 Workflows")

            // Toggle to the Chains tab. Best effort — the mode switch alone
            // already builds the collision, so a missing segment doesn't fail
            // the test.
            let chainsTab = app.buttons["Chains"].firstMatch
            if chainsTab.waitForExistence(timeout: 5) {
                chainsTab.click()
                assertStillForeground(iteration: iteration, step: "after Chains tab")
            }

            // Back to Library (⌃⌘1) — another toolbar rebuild.
            app.typeKey("1", modifierFlags: [.control, .command])
            assertStillForeground(iteration: iteration, step: "after ⌃⌘1 Library")
        }
    }

    /// A duplicate `.searchable` NSToolbar crash fires synchronously during the
    /// toolbar rebuild triggered by the mode switch, so give the rebuild a beat
    /// to complete + any NSException to surface, then assert the app is still
    /// foregrounded (a crash flips it to `.notRunning`).
    @MainActor
    private func assertStillForeground(iteration: Int, step: String) {
        // Deliberate settle window for the async toolbar rebuild + crash-if-any.
        Thread.sleep(forTimeInterval: 1.5)
        XCTAssertEqual(
            app.state,
            .runningForeground,
            "Cycle \(iteration): app left the foreground \(step) — a duplicate "
            + ".searchable NSToolbar crash (#3163)."
        )
    }
}
