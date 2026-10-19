@testable import Fichero
import Testing

/// Ready is grouped sections (#5840): the steps numbered in run order, then what runs by itself, the two optional parts,
/// and the last box.
struct ReadySectionsTests {
    @Test("each step is its own numbered box in run order, then the parts, the optional ones marked, Start last")
    func order() {
        let sections = ReadySection.order(steps: [(id: "s1", title: "Find Lines"), (id: "s2", title: "Read")])
        #expect(sections == [
            .step(number: 1, stepId: "s1", title: "Find Lines"), .step(number: 2, stepId: "s2", title: "Read"),
            .runsByItself, .checkOnYourPages, .keepAnExport, .start
        ])
        #expect(sections.map(\.title) == ["1. Find Lines", "2. Read", "What runs by itself", "Check on your pages",
                                          "Keep an export", "Start"])
        #expect(sections.filter(\.isOptional) == [.checkOnYourPages, .keepAnExport])
    }

    @Test("with no steps the parts still follow in order")
    func noSteps() {
        #expect(ReadySection.order(steps: []) == [.runsByItself, .checkOnYourPages, .keepAnExport, .start])
    }
}

struct ReadyRefusalTests {
    @Test("a refusal names its step's job, or none")
    func refusalJob() {
        #expect(RecipeStartFields.job(ofRefusal: "step 1 (find-regions): no model") == "find-regions")
        #expect(RecipeStartFields.job(ofRefusal: "Nothing to run") == nil)
    }
}
