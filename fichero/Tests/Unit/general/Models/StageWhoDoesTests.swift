//
//  StageWhoDoesTests.swift
//  FicheroTests
//
//  #5838: Find Lines says on screen which finders can find lines; no other stage says it.
//

@testable import Fichero
import XCTest

final class StageWhoDoesTests: XCTestCase {
    func testFindLinesNamesTheLineFindersAndSaysCloudModelsCannot() throws {
        let words = try XCTUnwrap(StageCandidateChooser.whoDoes(stageId: "find-lines"))
        for name in ["Kraken", "Apple Vision", "Cloud vision models can't find lines"] {
            XCTAssertTrue(words.contains(name), name)
        }
    }

    func testOtherStagesSayNothing() {
        XCTAssertNil(StageCandidateChooser.whoDoes(stageId: "read"))
    }
}
