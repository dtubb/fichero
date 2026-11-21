//
//  SearchWithInspectorClosedUITests.swift
//  FicheroUITests
//
//  `search.always-visible` (#6729): closing the inspector keeps search. On the Mac the toolbar search field is a
//  toolbar item of the inspector column (`ContentView+InspectorContainer`), so this drives the real window: close the
//  inspector, then the field must still be in the toolbar, hittable, and take typed text.
//
//  The field is clicked, not reached with ⌘F: on the Mac ⌘F focuses the library's filter field
//  (`LibraryView+FilterAndBatch`), not the toolbar search.
//
//  Reuses the shared-session harness (FicheroUISessionTests, #4246), which opens a seeded document with the
//  inspector shown.
//

import XCTest

@MainActor
final class SearchWithInspectorClosedUITests: FicheroUISessionTests {

    func testSearchFieldStaysUsableWithTheInspectorClosed() throws {
        waitForLibraryReady()

        // An inspector section button is on screen only while the inspector is open.
        let inspectorSection = app.buttons["inspectorSection-Knowledge"]
        XCTAssertTrue(
            inspectorSection.waitForExistence(timeout: readyTimeout),
            "The inspector was not open at the start, so closing it proves nothing."
        )

        app.typeKey("i", modifierFlags: [.control, .command])
        defer { app.typeKey("i", modifierFlags: [.control, .command]) }
        let closed = NSPredicate(format: "exists == false")
        XCTAssertEqual(
            XCTWaiter().wait(for: [expectation(for: closed, evaluatedWith: inspectorSection)], timeout: 10),
            .completed,
            "⌃⌘I did not close the inspector."
        )

        let field = app.searchFields["toolbar.search"]
        XCTAssertTrue(
            field.waitForExistence(timeout: 10),
            "The toolbar search field left the window with the inspector closed."
        )
        XCTAssertTrue(field.isHittable, "The toolbar search field is in the tree but not on screen.")

        field.click()
        field.typeText("Córdoba")
        XCTAssertEqual(
            field.value as? String, "Córdoba",
            "The toolbar search field did not take focus and typing with the inspector closed."
        )
        field.typeKey(.escape, modifierFlags: [])
    }
}
