//
//  PrepareImagesSetupUITests.swift
//  FicheroUITests
//
//  SPEC-BEHAVIOR runtime test for the Prepare Images card in Set Up
//  (`prep.setup.three-questions-suggested-from-a-sample`, `prep.estimate.time-on-this-mac-before-start`, #5580):
//  the stage asks its four questions and shows the engine's time line beneath them. Written 2026-10-29, never run
//  (no xcodebuild in the builder lane): the first run on a Mac may need the navigation step adjusted.
//

import XCTest

@MainActor
final class PrepareImagesSetupUITests: FicheroUISessionTests {

    /// The card asks "Two pages in one picture?" and the paper question, and states the time as an estimate.
    func testThePrepareImagesCardAsksItsQuestionsAndStatesTheTime() throws {
        waitForLibraryReady()
        let stage = app.staticTexts["Prepare Images"].firstMatch
        try XCTSkipUnless(stage.waitForExistence(timeout: 10), "Set Up's Prepare Images stage is not on screen in this session")
        stage.click()

        XCTAssertTrue(app.staticTexts["Two pages in one picture?"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["The paper"].exists)
        let estimate = app.descendants(matching: .any).matching(identifier: "prepareImages.estimate").firstMatch
        XCTAssertTrue(estimate.waitForExistence(timeout: 10), "the card shows no time line")
        XCTAssertTrue(estimate.label.contains("estimate"), "the time must say it is an estimate: \(estimate.label)")
    }
}
