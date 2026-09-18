//
//  WorkspaceApplyResponsivenessUITests.swift
//  FicheroUITests
//
//  SPEC-BEHAVIOR test for the workspace system — the RUNTIME reproduction the
//  structural unit tests could not give.
//
//  Why this suite exists: the pure-model guard
//  `BuiltInWorkspaceLayoutTests.everyBuiltInIsInstanceSafe` passed GREEN while the
//  app BEACHBALLED when applying the "Compare" workspace (spec
//  §"CD runtime review 2026-09-15" / panes.instance-safe). The reason is spelled
//  out in the spec: the fault is a *Scene-level focused-value collision* — two
//  same-kind pane leaves both publish the same `focusedSceneValue` keys per frame
//  → SwiftUI's "FocusedValue update tried to update multiple times per frame"
//  fault → a recursive scene-graph invalidation / remount storm → a 30-second
//  hang. A model test has no Scene and no `@FocusedValue` environment, so it
//  CANNOT reproduce a "multiple updates per frame" fault. Only an XCUITest that
//  applies each workspace against a real `WindowGroup` Scene and then asserts a
//  follow-up interaction completes within N seconds can catch it (spec
//  §"Testing this class", item 2).
//
//  A beachball is NOT a crash: the app stays `.runningForeground` the whole time
//  its main thread is wedged, so a process-state assertion (the
//  ToolbarModeLaunchStress oracle) would PASS through a hang. The only honest
//  oracle for "the main thread is still servicing its run loop" is an INTERACTION
//  that requires the run loop — opening a menu and reading its contents. Menu
//  tracking is driven by the app's main run loop, so if the main thread is
//  beachballed the menu never opens and `waitForExistence` times out → the test
//  fails. THIS is the assertion that would have caught the Compare beachball.
//
//  Pins: `panes.instance-safe` (a workspace may mount more than one pane of the
//  same kind in one window without a focused-value collision / remount storm).
//
//  Reuses the shared-session harness (FicheroUISessionTests, #4246): ONE engine,
//  ONE seeded library, ONE app launch for the whole run. Applying a workspace is
//  cheap against the live session, so all six are exercised in one test.
//

import XCTest

@MainActor
final class WorkspaceApplyResponsivenessUITests: FicheroUISessionTests {

    /// The FIVE built-in workspaces in ⌘⌥1–5 slot order (spec §"v2 workspace
    /// design" / `BuiltInWorkspaceLayout` declaration order). Kept as literals —
    /// the UI-test target does not link the app module, so it cannot reference
    /// `BuiltInWorkspaceLayout`; and the spec's ruling is that these tests assert
    /// the BEHAVIOR (the menu title the user sees, the shortcut they press), never
    /// the code's symbols.
    private static let workspaces: [(slot: Int, key: String, title: String)] = [
    /// Was six, ending in Catalogue and Claims, until the creative director cut
    /// them (2026-09-16). Slot 4 is now Transcribe · Tall and Compare moved to 5,
    /// so the old table also pressed the WRONG shortcut for Compare — the very
    /// workspace whose beachball this suite exists to catch. Keep in sync with
    /// `BuiltInWorkspaceLayout.allCases`; ⌘⌥6–9 are free for user workspaces.
        (1, "1", "Read"),
        (2, "2", "Browse"),
        (3, "3", "Transcribe"),
        (4, "4", "Transcribe · Tall"),
        (5, "5", "Compare")       // the beachball workspace (two previews + two readers)
    ]

    /// A beachball longer than this fails the test. The observed Compare hang was
    /// ~30s (spec panes.instance-safe); a healthy menu open resolves in well under
    /// a second, so 8s is a generous ceiling that still fails a real hang fast.
    private let responsivenessTimeout: TimeInterval = 8

    // MARK: - The crash-catcher

    /// Apply EACH built-in workspace and assert the app stays RESPONSIVE after
    /// each one. Prefers the ⌘⌥N key equivalent (the shortcut the user presses),
    /// falling back to the View ▸ Workspaces menu item by title if the key
    /// equivalent does not take. After each apply the responsiveness probe opens a
    /// menu — a live-run-loop interaction — so a beachball (spec
    /// `panes.instance-safe`) makes the probe time out and the test fail.
    func testEveryWorkspaceStaysResponsiveAfterApply() throws {
        waitForLibraryReady()

        for workspace in Self.workspaces {
            // Clear any transient focus so the key equivalent is not swallowed by
            // a text field, then apply the workspace by its shortcut.
            app.typeKey(.escape, modifierFlags: [])
            applyWorkspace(workspace)

            // spec panes.instance-safe: applying a workspace with two of the same
            // pane kind (Compare) must NOT wedge the main thread. Probe liveness.
            assertResponsive(
                after: "applying the \"\(workspace.title)\" workspace (⌘⌥\(workspace.key))"
            )

            // A remount storm can also eventually crash rather than hang — the
            // shared session drops out of the foreground if it does.
            XCTAssertEqual(
                app.state, .runningForeground,
                "App left the foreground after applying \"\(workspace.title)\" — "
                + "a crash while composing the workspace (spec panes.instance-safe)."
            )
        }
    }

    // MARK: - Apply

    /// Apply a workspace, preferring its ⌘⌥N key equivalent; if the app does not
    /// respond to a follow-up menu open afterwards we assume the key equivalent
    /// was swallowed and re-apply through the View ▸ Workspaces menu by title
    /// (spec deliverable: "prefer ⌘⌥1–5 … fall back to the menu items by title").
    private func applyWorkspace(_ workspace: (slot: Int, key: String, title: String)) {
        // ⌘⌥N — command+option, distinct from the ⌃⌘N sidebar-mode shortcuts the
        // session's resetToKnownState uses.
        app.typeKey(workspace.key, modifierFlags: [.command, .option])

        // Give the compose/render a beat to settle (or to start hanging).
        Thread.sleep(forTimeInterval: 0.75)

        // If the app is already wedged, the menu-based fallback cannot help — the
        // responsiveness assertion below will report it. If it is alive but the
        // key equivalent silently did nothing, the menu path applies it
        // deterministically.
        if !viewMenuResponds(timeout: 2) {
            return   // wedged — let assertResponsive() fail with the real message
        }
        applyViaMenu(title: workspace.title)
    }

    /// Deterministic fallback: View ▸ Workspaces ▸ <title>.
    private func applyViaMenu(title: String) {
        let viewMenu = app.menuBars.menuBarItems["View"]
        guard viewMenu.waitForExistence(timeout: 5) else { return }
        viewMenu.click()
        let workspacesItem = app.menuItems["Workspaces"]
        guard workspacesItem.waitForExistence(timeout: 3) else {
            app.typeKey(.escape, modifierFlags: [])
            return
        }
        workspacesItem.click()   // open the flyout
        let item = app.menuItems[title]
        if item.waitForExistence(timeout: 3) {
            item.click()
        } else {
            app.typeKey(.escape, modifierFlags: [])
        }
        Thread.sleep(forTimeInterval: 0.75)
    }

    // MARK: - Responsiveness oracle (main-thread liveness)

    /// Assert the app can still service its run loop by opening the View menu and
    /// waiting for a known item to appear within `responsivenessTimeout`. A
    /// beachball wedges the main thread → menu tracking never starts → timeout →
    /// failure. (spec panes.instance-safe — the runtime reproduction.)
    private func assertResponsive(after context: String) {
        XCTAssertTrue(
            viewMenuResponds(timeout: responsivenessTimeout),
            "App did not respond within \(Int(responsivenessTimeout))s after \(context) — "
            + "the main thread is wedged (a beachball / remount storm), exactly the "
            + "panes.instance-safe failure a structural model test cannot see."
        )
        // Dismiss the menu we opened so the next iteration starts clean.
        app.typeKey(.escape, modifierFlags: [])
    }

    /// Open the View menu and report whether its "Workspaces" item appears within
    /// `timeout`. Leaves the menu closed. Used both as the liveness oracle and to
    /// decide whether the key-equivalent apply needs the menu fallback.
    private func viewMenuResponds(timeout: TimeInterval) -> Bool {
        let viewMenu = app.menuBars.menuBarItems["View"]
        guard viewMenu.waitForExistence(timeout: min(timeout, 5)) else { return false }
        viewMenu.click()
        let responded = app.menuItems["Workspaces"].waitForExistence(timeout: timeout)
        app.typeKey(.escape, modifierFlags: [])
        return responded
    }
}
