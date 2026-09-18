//
//  WorkspaceMountUITests.swift
//  FicheroUITests
//
//  Mounts every built-in workspace and asserts its expected panes actually
//  APPEAR by accessibility identifier (spec panes.one-renderer). Applying a
//  workspace crosses a hosting boundary per pane (PaneSpec.swift): a missing
//  @Environment object there SIGTRAPs with NO app frame in the stack — the
//  "No Observable object of type X found" crash class (2026-09-17,
//  WorkflowExecutionObserver). Nothing short of actually switching to each
//  workspace and querying for its panes catches that: a unit test never mounts
//  the SwiftUI tree far enough to see it.
//
//  Mirrors `BuiltInWorkspaceLayout.panes` (fichero/Views/Shell/WindowLayout/
//  BuiltInWorkspaceLayout.swift) as a literal table — the UI-test target does
//  not link the app module, so it cannot import the real enum (same constraint
//  WorkspaceAccessibilityUITests documents). Keep this table in sync when a
//  workspace's composition changes; a workspace or pane kind renamed there and
//  not here fails loud (missing menu item / missing pane identifier), it does
//  not silently stop testing anything.
//
//  Reuses the shared-session harness (FicheroUISessionTests, #4246): one engine,
//  one seeded library, one launch — this suite just switches workspaces inside it.
//

import XCTest

@MainActor
final class WorkspaceMountUITests: FicheroUISessionTests {

    private struct Workspace {
        let key: String    // ⌘⌥<key>, BuiltInWorkspaceLayout.defaultSlot order
        let title: String  // exact menu-item title (BuiltInWorkspaceLayout.title)
        /// Distinct `PaneKind.rawValue`s the composition contains — every leaf's
        /// `pane.<kind>` accessibility identifier must be mountable. A kind
        /// repeated in the composition (e.g. Compare's two previews) only needs
        /// one entry: presence, not count, is what a hosting-boundary crash removes.
        let expectedPaneKinds: Set<String>
    }

    /// Declaration order == default ⌘⌥1–5 slot order.
    private static let workspaces: [Workspace] = [
        Workspace(key: "1", title: "Read", expectedPaneKinds: ["library", "reading", "preview"]),
        Workspace(key: "2", title: "Browse", expectedPaneKinds: ["library", "preview", "reading"]),
        Workspace(key: "3", title: "Transcribe", expectedPaneKinds: ["preview", "reading", "library"]),
        Workspace(
            key: "4", title: "Transcribe · Tall",
            expectedPaneKinds: ["preview", "reading", "library"]
        ),
        Workspace(key: "5", title: "Compare", expectedPaneKinds: ["preview", "reading", "library"])
    ]

    /// Switch to every built-in workspace and confirm its panes MOUNT — not just
    /// that the shell stayed alive, but that each expected pane kind's own
    /// accessibility identifier is queryable in the composed tree.
    func testEveryBuiltInWorkspaceMountsItsExpectedPanes() throws {
        waitForLibraryReady()

        for workspace in Self.workspaces {
            app.typeKey(.escape, modifierFlags: [])
            app.typeKey(workspace.key, modifierFlags: [.command, .option])

            // The shell itself is still up. A hosting-boundary crash on a pane
            // takes the WHOLE window with it — no app frame, no per-pane crash
            // log — so losing this anchor is the first and loudest signal.
            XCTAssertTrue(
                LaunchReadiness.waitUntilReady(app, timeout: readyTimeout),
                "Switching to \"\(workspace.title)\" (⌘⌥\(workspace.key)) lost the shell's "
                + "content-ready anchor (`library.content.ready`) — the app likely crashed "
                + "mounting this workspace's panes."
            )

            for kind in workspace.expectedPaneKinds.sorted() {
                let identifier = "pane.\(kind)"
                let pane = app.descendants(matching: .any).matching(identifier: identifier).firstMatch
                XCTAssertTrue(
                    pane.waitForExistence(timeout: 8),
                    "\"\(workspace.title)\" (⌘⌥\(workspace.key)) never mounted its \"\(kind)\" "
                    + "pane — no element with accessibility identifier \"\(identifier)\" appeared. "
                    + "Expected pane kinds for this workspace: "
                    + "\(workspace.expectedPaneKinds.sorted().joined(separator: ", "))."
                )
            }
        }
    }
}
