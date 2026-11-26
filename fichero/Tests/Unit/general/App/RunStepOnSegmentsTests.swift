@testable import Fichero
import Testing

/// `segment-actions.run-step-on-selection` (#6069): the menu item names the step and counts what is selected, and the
/// menu is offered only with a selection and steps to run. What breaks without these: a Run Step item that does not say
/// what it will run on, or a menu on nothing.
@Suite("Run Step on the selected segments (#6069)")
struct RunStepOnSegmentsTests {
    @Test("the item names the step and the count of segments")
    func itemTitle() {
        #expect(RunStepOnSegmentsMenu.itemTitle(step: "Read", count: 2) == "Run Read on 2 segments")
        #expect(RunStepOnSegmentsMenu.itemTitle(step: "Translate", count: 1) == "Run Translate on 1 segment")
    }

    @Test("the items menu on pages names the step and counts pages the same way")
    func itemsTitle() {
        #expect(RunStepAgainOnSelectionMenu.itemTitle(step: "Read", count: 3) == "Run Read on 3 pages")
        #expect(RunStepAgainOnSelectionMenu.itemTitle(step: "Read", count: 1) == "Run Read on 1 page")
    }

    @Test("the menu is Run Step, as on every surface, and shown only with a selection and steps")
    func offered() {
        #expect(RunStepOnSegmentsMenu.title == RunStepAgainOnSelectionMenu.title)
        #expect(RunStepOnSegmentsMenu.isOffered(ids: ["a"], stepCount: 1))
        #expect(!RunStepOnSegmentsMenu.isOffered(ids: [], stepCount: 3))
        #expect(!RunStepOnSegmentsMenu.isOffered(ids: ["a"], stepCount: 0))
    }
}
