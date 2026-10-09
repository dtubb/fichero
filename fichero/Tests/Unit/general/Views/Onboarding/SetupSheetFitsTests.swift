@testable import Fichero
import SwiftUI
import XCTest

#if os(macOS)
/// The Set Up sheet fits its window (#5624, the maintainer testing 2322e2b01): on What you want
/// to do, the six "Which kinds of names" checkboxes sat in one fixed-size row, wider than the
/// step's column, so the sheet grew past its window and cut off the step list and Continue.
/// What breaks without this: a row of setup goes back to one unbreakable line, and a long enough
/// one pushes the button row off the sheet again. Measured through SwiftUI's own layout, not a
/// source scan: each row is asked to fit a column narrower than its one-line width.
@MainActor
final class SetupSheetFitsTests: XCTestCase {
    /// Narrower than the six kinds of names side by side (about 560 points), and than the step
    /// column beside the sidebar (820 − 230 − padding).
    private let column: CGFloat = 320

    private func width(of view: some View) -> CGFloat {
        NSHostingController(rootView: view).sizeThatFits(in: CGSize(width: column, height: 10_000)).width
    }

    private func store() -> RecipeSetupStore {
        RecipeSetupStore(client: FicheroClient(libraryPath: nil))
    }

    func testTheKindsOfNamesWrapToTheColumn() {
        let measured = width(of: JobQuestionFields(store: store(), job: "find-names-tag-words"))
        XCTAssertLessThanOrEqual(measured, column, "the kinds of names wrap; they never widen the sheet")
    }

    func testManyLanguageTokensAndTheMaterialsWrapToTheColumn() {
        let store = store()
        for (code, name) in [("es", "Spanish"), ("la", "Latin"), ("pt", "Portuguese"), ("ca", "Catalan"),
                             ("fr", "French"), ("it", "Italian"), ("de", "German"), ("nl", "Dutch")] {
            store.add(.init(code: code, name: name, detail: nil), toScripts: false)
        }
        XCTAssertLessThanOrEqual(width(of: RecipeAboutFields(store: store)), column,
                                 "eight languages as tokens, and the kinds of material, wrap to the column")
    }
}
#endif
