//
//  WorkspaceReadCompositionUITests.swift
//  FicheroUITests
//
//  SPEC-BEHAVIOR runtime tests for the "Read" workspace composition — the two
//  faults a pure model test cannot see because they are about what MOUNTS in a
//  real Scene, not what the `PaneList` value contains:
//
//    1. panes.read.one-library — "Read shows TWO library panes" (CD live
//       2026-09-16). The Read model composes exactly one library leaf
//       (asserted by BuiltInWorkspaceLayoutTests), so a second library at
//       runtime is a MOUNTING fault, catchable only against a live window.
//    2. panes.close.this-pane-only — "closing one pane closes BOTH." The model
//       + close seam are asserted structurally (WorkspaceSystemBoundaryTests);
//       this is the runtime reproduction: close one pane, the sibling stays.
//
//  Each applied leaf carries a per-kind accessibility identifier
//  ("pane.library" / "pane.preview" / "pane.reading") published by
//  ContentView.paneNodeView on the applied-workspace path, so the composed
//  panes are countable. Read is applied through View ▸ Workspaces ▸ Read (the
//  deterministic menu path) so a swallowed ⌘⌥1 shortcut does not conflate this
//  composition test with the shortcut-uniqueness suite.
//
//  Reuses the shared-session harness (FicheroUISessionTests, #4246).
//

import XCTest

@MainActor
final class WorkspaceReadCompositionUITests: FicheroUISessionTests {

    /// The per-kind identifiers the applied path publishes on each leaf.
    private static let paneKindIdentifiers = ["pane.library", "pane.preview", "pane.reading", "pane.inspector"]

    // MARK: - Bug 1: Read shows exactly one library pane

    /// spec panes.read.one-library: after applying Read, exactly ONE library pane is mounted
    /// ("Read shows TWO library panes" was the reported bug). Counts the `pane.library`
    /// accessibility identifier the applied renderer stamps on each library leaf.
    func testReadWorkspaceMountsExactlyOneLibraryPane() throws {
        waitForLibraryReady()
        applyReadWorkspace()

        let libraryPanes = app.descendants(matching: .any).matching(identifier: "pane.library")
        XCTAssertTrue(
            libraryPanes.firstMatch.waitForExistence(timeout: 10),
            "After applying Read no `pane.library` mounted — the workspace did not compose its library."
        )
        XCTAssertEqual(
            libraryPanes.count, 1,
            "Read mounted \(libraryPanes.count) library panes — the spec is exactly one library, "
            + "over the reader and beside the preview (spec panes.read.one-library)."
        )
    }

    // MARK: - Bug 2: closing one pane leaves the sibling

    /// spec panes.close.this-pane-only: closing ONE pane in the applied Read workspace removes only
    /// that pane — the siblings stay. Reproduces "closing one pane closes BOTH": counts the composed
    /// panes, clicks one pane head's close button, and asserts the count drops by exactly one (not
    /// to zero / not the whole row) and the library survives.
    func testClosingOnePaneKeepsTheSiblings() throws {
        waitForLibraryReady()
        applyReadWorkspace()

        let before = mountedPaneCount()
        XCTAssertGreaterThanOrEqual(
            before, 2,
            "Read should compose at least two panes to test independent close (saw \(before))."
        )

        // Click one pane head's close affordance ("Close pane" / "Close this split").
        let close = app.buttons
            .matching(NSPredicate(format: "label BEGINSWITH %@", "Close")).firstMatch
        guard close.waitForExistence(timeout: 8), close.isHittable else {
            throw XCTSkip("No hittable pane-head close control found — cannot drive the close interaction.")
        }
        close.click()
        Thread.sleep(forTimeInterval: 0.75)

        let after = mountedPaneCount()
        XCTAssertEqual(
            after, before - 1,
            "Closing one pane changed the mounted pane count from \(before) to \(after) — closing a "
            + "single pane must remove exactly one (closing BOTH / the whole row is the bug, spec "
            + "panes.close.this-pane-only)."
        )
        XCTAssertGreaterThanOrEqual(
            after, 1,
            "Closing one pane emptied the window — the sibling pane must remain."
        )
        XCTAssertEqual(
            app.state, .runningForeground,
            "The app left the foreground after closing a pane in Read."
        )
    }

    // MARK: - Helpers

    /// The number of applied-workspace leaves currently mounted, by their per-kind identifiers.
    private func mountedPaneCount() -> Int {
        Self.paneKindIdentifiers.reduce(0) { total, identifier in
            total + app.descendants(matching: .any).matching(identifier: identifier).count
        }
    }

    /// Apply Read deterministically through View ▸ Workspaces ▸ Read (so a swallowed ⌘⌥1 does not
    /// make this composition test fail for a shortcut reason — that is the shortcut suite's job).
    private func applyReadWorkspace() {
        app.typeKey(.escape, modifierFlags: [])
        let viewMenu = app.menuBars.menuBarItems["View"]
        guard viewMenu.waitForExistence(timeout: 10) else {
            XCTFail("No View menu in the menu bar — cannot apply the Read workspace."); return
        }
        viewMenu.click()
        let workspacesItem = app.menuItems["Workspaces"]
        guard workspacesItem.waitForExistence(timeout: 5) else {
            XCTFail("View ▸ Workspaces is missing."); return
        }
        workspacesItem.click()
        let read = app.menuItems["Read"]
        if read.waitForExistence(timeout: 5) {
            read.click()
        } else {
            XCTFail("View ▸ Workspaces ▸ Read is missing.")
        }
        Thread.sleep(forTimeInterval: 1.0)
    }
}
