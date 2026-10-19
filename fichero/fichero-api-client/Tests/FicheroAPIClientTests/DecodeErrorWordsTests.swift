import Foundation
import XCTest
@testable import FicheroAPIClient

/// `Error.inWords`: a decode failure names the field and where (owner, 2026-10-19: Set Up said "The data couldn't be
/// read because it is missing"). The recipe a project saved without `problems` is the real case.
final class DecodeErrorWordsTests: XCTestCase {
    func testAMissingRecipeFieldIsNamedWithItsPath() throws {
        let recipe = Data(#"{"id":"r","title":"t","purposes":[],"steps":[],"gaps":[]}"#.utf8)
        XCTAssertThrowsError(try JSONDecoder().decode(Components.Schemas.AssembledRecipe.self, from: recipe)) { error in
            XCTAssertTrue(error.inWords.contains("\"problems\""), error.inWords)
            XCTAssertFalse(error.inWords.contains("couldn't be read"), error.inWords)
        }
    }

    func testAWholeRecipeDecodes() throws {
        let recipe = Data(#"{"id":"r","title":"t","purposes":[],"steps":[],"gaps":[],"problems":[]}"#.utf8)
        XCTAssertNoThrow(try JSONDecoder().decode(Components.Schemas.AssembledRecipe.self, from: recipe))
    }

    func testAnotherErrorKeepsItsOwnWords() {
        struct Plain: LocalizedError { var errorDescription: String? { "engine is down" } }
        XCTAssertEqual(Plain().inWords, "engine is down")
    }
}
