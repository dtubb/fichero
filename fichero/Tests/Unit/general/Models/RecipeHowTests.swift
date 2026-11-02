@testable import Fichero
import Foundation
import Testing

/// How do you want to run this (`designer.how.*`): the answers as the engine keeps them, the page's place in the flow, what you have.
struct RecipeHowTests {
    @Test("nothing answered is not saved; answers save under the engine's names")
    func encoding() throws {
        func json(_ answers: RecipeSetupAnswers) throws -> [String: Any] {
            try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(answers)) as? [String: Any])
        }
        #expect(HowAnswers().isEmpty)
        #expect(try json(RecipeSetupAnswers())["how"] == nil)
        let how = HowAnswers(places: ["this-mac"], modelKind: "compare", matters: "privacy")
        let saved = try #require(try json(RecipeSetupAnswers(how: how))["how"] as? [String: Any])
        #expect(saved["places"] as? [String] == ["this-mac"])
        #expect(saved["model_kind"] as? String == "compare" && saved["matters"] as? String == "privacy")
    }

    @Test("a saved project's how reads back")
    func decoding() throws {
        let json = #"{"how":{"places":["cloud"],"model_kind":"large","matters":"quality"}}"#
        let saved = try JSONDecoder().decode(RecipeSetupAnswers.self, from: Data(json.utf8))
        #expect(saved.how == HowAnswers(places: ["cloud"], modelKind: "large", matters: "quality"))
    }

    @Test("the How page sits after About the Material and before the stages, only in the wide Set Up")
    func flow() {
        let plain = SetupStep.projectSteps(chosenStages: ["read"], isNewProject: false)
        #expect(plain == [.addMaterial, .aboutMaterial, .stages, .stage("read"), .ready])
        let wide = SetupStep.projectSteps(chosenStages: ["read"], isNewProject: false, withHow: true)
        #expect(wide == [.addMaterial, .aboutMaterial, .how, .stages, .stage("read"), .ready])
        #expect(SetupStep.how.savesDraft && SetupStep.how.title() == "How")
        var flow = SetupFlow(includesApp: false, project: .existing)
        flow.includesHow = true
        #expect(flow.steps.contains(.how))
    }

    @Test("a place ticks on and off like any tick")
    func ticks() {
        #expect(RecipeSetupStore.toggled(nil, "cloud") == ["cloud"])
        #expect(RecipeSetupStore.toggled(["this-mac", "cloud"], "cloud") == ["this-mac"])
    }

    @Test("what you have is one sentence from the derived facts")
    func whatYouHave() {
        let line = RecipeSetupStore.whatYouHave(chip: "Apple M4", memoryGb: 16, keys: ["anthropic"], places: ["This Mac"])
        #expect(line == "This Mac: Apple M4, 16 GB of memory; keys saved for anthropic; work can run on This Mac.")
        #expect(RecipeSetupStore.whatYouHave(chip: nil, memoryGb: nil, keys: [], places: []) == "no provider keys saved.")
    }
}
