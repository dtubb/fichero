//
//  ReaderArrowKeysUITests.swift
//  FicheroUITests
//
//  #6474 (P1): Up/Down (#6457) did nothing in the real window although SelectionStepsAcrossSurfacesTests passed -- those
//  tests call InspectorPath.stepSelection directly and never reach a key press. This drives the real window: open the
//  seeded letter (three lines, `seed_test_library.add_letter_lines`), show the Reader's Lines tab, click a line, press
//  Down / Up / Shift+Down, and read which rows `reader.line.row` reports as selected.
//
//  WRITTEN, NOT YET RUN. XCUITest needs the Pro's GUI session (the manager runs it): test id
//  `FicheroUITests/ReaderArrowKeysUITests`.
//
//  Edit > Mark Unclear (#6454) is deliberately NOT tested here: commit 180e3fd4c8 removed the menu and chord because nothing
//  published a selection for it, so there is no item to enable. When it is rebuilt with a publisher, its window test goes here.
//

import XCTest

@MainActor
final class ReaderArrowKeysUITests: FicheroUISessionTests {
    private var rows: XCUIElementQuery { app.descendants(matching: .any).matching(identifier: "reader.line.row") }

    /// The indices (top to bottom) of the rows the shared selection has lit.
    private func selectedRows() -> [Int] {
        (0..<rows.count).filter { rows.element(boundBy: $0).value as? String == "selected" }
    }

    private func openLines() {
        waitForLibraryReady()
        let lines = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'Lines'")).firstMatch
        XCTAssertTrue(lines.waitForExistence(timeout: readyTimeout), "The Reader's Lines tab never appeared.")
        lines.click()
        XCTAssertTrue(
            rows.element(boundBy: 2).waitForExistence(timeout: readyTimeout),
            "The letter shows fewer than three lines -- the harness did not add its lines (add_letter_lines)."
        )
    }

    func testDownAndUpStepTheSelectionThroughTheLines() {
        openLines()
        rows.element(boundBy: 0).click()
        XCTAssertEqual(selectedRows(), [0], "Clicking the first line should select it alone.")

        app.typeKey(.downArrow, modifierFlags: [])
        XCTAssertEqual(selectedRows(), [1], "Down should move the selection to the next line.")

        app.typeKey(.downArrow, modifierFlags: [])
        XCTAssertEqual(selectedRows(), [2])

        app.typeKey(.upArrow, modifierFlags: [])
        XCTAssertEqual(selectedRows(), [1], "Up should move the selection back one line.")
    }

    func testShiftDownExtendsTheSelection() {
        openLines()
        rows.element(boundBy: 0).click()
        app.typeKey(.downArrow, modifierFlags: .shift)
        XCTAssertEqual(selectedRows(), [0, 1], "Shift+Down should add the next line to the selection.")
    }

    func testDownWithNothingSelectedStartsAtTheFirstLine() {
        openLines()
        app.typeKey(.escape, modifierFlags: [])
        app.typeKey(.downArrow, modifierFlags: [])
        XCTAssertEqual(selectedRows(), [0], "With nothing selected Down should select the first line (#6474).")
    }
}
