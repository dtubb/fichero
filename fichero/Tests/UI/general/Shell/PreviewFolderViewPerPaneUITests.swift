//
//  PreviewFolderViewPerPaneUITests.swift
//  FicheroUITests
//
//  SPEC-BEHAVIOR runtime test for `library.preview.folder-view-per-pane` and
//  `library.preview.folder-view-picker-in-the-head` (#6365): each Preview pane's head offers
//  Canvas, List and Table in its own selector menu, and the two panes of Compare (two Previews)
//  each carry their own copy of that menu. The pure rules (default Table, per-pane write, split
//  copy, relaunch round trip through the remembered pane list) are pinned by
//  PreviewFolderViewPerPaneTests; this suite proves the menu MOUNTS in each real pane head.
//
//  Reuses the shared-session harness (FicheroUISessionTests, #4246).
//

import XCTest

@MainActor
final class PreviewFolderViewPerPaneUITests: FicheroUISessionTests {

    private static let entries = ["canvas", "list", "table"].map { "previewHeadFolderView.\($0)" }

    /// Compare mounts two Preview panes; each head's selector menu carries the three folder views.
    func testEveryPreviewPaneHeadOffersCanvasListAndTable() throws {
        waitForLibraryReady()
        applyWorkspace("Compare")

        let previews = app.descendants(matching: .any).matching(identifier: "pane.preview")
        XCTAssertTrue(previews.firstMatch.waitForExistence(timeout: 10), "Compare mounted no `pane.preview`.")
        XCTAssertGreaterThanOrEqual(previews.count, 2, "Compare should mount two Preview panes.")

        for index in 0..<2 {
            let pane = previews.element(boundBy: index)
            let lensMenu = pane.menuButtons
                .matching(NSPredicate(format: "label BEGINSWITH %@", "View:")).firstMatch
            guard lensMenu.waitForExistence(timeout: 5) else {
                XCTFail("Preview pane \(index) has no View menu in its head."); continue
            }
            lensMenu.click()
            for identifier in Self.entries {
                XCTAssertTrue(
                    app.menuItems[identifier].waitForExistence(timeout: 5),
                    "Preview pane \(index)'s head menu is missing `\(identifier)`."
                )
            }
            app.typeKey(.escape, modifierFlags: [])
        }
    }

    /// Apply a built-in workspace through View ▸ Workspaces (the deterministic menu path).
    private func applyWorkspace(_ title: String) {
        app.typeKey(.escape, modifierFlags: [])
        let viewMenu = app.menuBars.menuBarItems["View"]
        guard viewMenu.waitForExistence(timeout: 10) else { XCTFail("No View menu."); return }
        viewMenu.click()
        let workspaces = app.menuItems["Workspaces"]
        guard workspaces.waitForExistence(timeout: 5) else { XCTFail("View ▸ Workspaces is missing."); return }
        workspaces.click()
        let item = app.menuItems[title]
        if item.waitForExistence(timeout: 5) { item.click() } else { XCTFail("Workspace \(title) is missing.") }
        Thread.sleep(forTimeInterval: 1.0)
    }
}
