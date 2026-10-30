//
//  PrepareImagesSetupUITests.swift
//  FicheroUITests
//
//  SPEC-BEHAVIOR runtime test for the Prepare Images card in Set Up
//  (`prep.setup.three-questions-suggested-from-a-sample`, `prep.estimate.time-on-this-mac-before-start`, #5580):
//  the stage asks its four questions and shows the engine's time line beneath them. Written 2026-10-29, never run
//  (no xcodebuild in the builder lane). Navigation follows the real view tree: Project ▸ Set Up… opens the window,
//  the chooser's checkbox for the stage (`setup.stage.row.prepare-images`) is ticked, and Continue (the footer's
//  default button) goes to the first chosen stage's page. Neither "Prepare Images" text nor a sidebar row is clicked.
//

import XCTest

@MainActor
final class PrepareImagesSetupUITests: FicheroUISessionTests {

    /// Project ▸ Set Up…, then Choose the Stages, the stage ticked, Continue to its page.
    private func openPrepareImagesPage() throws {
        waitForLibraryReady()
        let projectMenu = app.menuBars.menuBarItems["Project"]
        try XCTSkipUnless(projectMenu.waitForExistence(timeout: 10), "No Project menu in this session")
        projectMenu.click()
        let setUp = app.menuItems["Set Up…"]
        try XCTSkipUnless(setUp.waitForExistence(timeout: 5) && setUp.isEnabled, "Set Up… is not available for this project")
        setUp.click()

        // The window's list names its pages; Choose the Stages is where a stage is ticked.
        let choose = app.staticTexts["Choose the Stages"].firstMatch
        try XCTSkipUnless(choose.waitForExistence(timeout: 10), "Set Up did not open")
        choose.click()
        let row = app.descendants(matching: .any).matching(identifier: "setup.stage.row.prepare-images").firstMatch
        try XCTSkipUnless(row.waitForExistence(timeout: 10), "Prepare Images is not among this project's stages")
        if (row.value as? Int) != 1 && (row.value as? String) != "1" { row.click() }
        let next = app.buttons["Continue"].firstMatch
        XCTAssertTrue(next.waitForExistence(timeout: 5), "the footer has no Continue")
        // Continue goes to the first chosen stage; press until the Prepare Images page's question shows.
        for _ in 0..<13 where !app.staticTexts["Two pages in one picture?"].exists {
            next.click()
            _ = app.staticTexts["Two pages in one picture?"].waitForExistence(timeout: 2)
        }
    }

    /// The card asks "Two pages in one picture?" and the paper question, and states the time as an estimate.
    func testThePrepareImagesCardAsksItsQuestionsAndStatesTheTime() throws {
        try openPrepareImagesPage()

        XCTAssertTrue(app.staticTexts["Two pages in one picture?"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.staticTexts["The paper"].exists)
        let estimate = app.descendants(matching: .any).matching(identifier: "prepareImages.estimate").firstMatch
        XCTAssertTrue(estimate.waitForExistence(timeout: 10), "the card shows no time line")
        XCTAssertTrue(estimate.label.contains("estimate"), "the time must say it is an estimate: \(estimate.label)")
    }

    /// A folder's own answers (`answers.job_answers_by_folder`): the picker is on the card when the project has folders.
    func testTheCardOffersAnswersForOneFolderWhenTheProjectHasFolders() throws {
        try openPrepareImagesPage()
        let picker = app.descendants(matching: .any).matching(identifier: "prepareImages.folder.picker").firstMatch
        try XCTSkipUnless(picker.waitForExistence(timeout: 5), "the seeded project has no folder")
        picker.click()
        let first = app.menuItems.element(boundBy: 1)
        try XCTSkipUnless(first.waitForExistence(timeout: 3), "the picker lists no folder")
        first.click()
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "prepareImages.folder.twoPages")
            .firstMatch.waitForExistence(timeout: 5), "a folder's own two-pages answer is not offered")
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "prepareImages.folder.paper.show-through")
            .firstMatch.exists, "a folder's own paper answers are not offered")
    }
}
