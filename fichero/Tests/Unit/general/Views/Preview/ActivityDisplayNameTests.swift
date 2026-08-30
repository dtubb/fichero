@testable import Fichero
import Testing

struct ActivityDisplayNameTests {
    @Test("Identifier mapping uses user-facing labels for known artifact names")
    func identifierKnownMapping() {
        #expect(activityDisplayName(forIdentifier: "page_content") == "Page Content")
        #expect(activityDisplayName(forIdentifier: "extract_all_entities") == "Extract Entities")
    }

    @Test("Identifier mapping falls back to title case for snake case")
    func identifierFallback() {
        #expect(activityDisplayName(forIdentifier: "custom_step_name") == "Custom Step Name")
    }

    @Test("Activity message humanization rewrites internal artifact tokens")
    func messageHumanization() {
        let raw = "Saved artifact_type=page_content for node=extract_all_entities"
        let pretty = activityHumanizeMessage(raw)
        #expect(pretty.contains("artifact_type=Page Content"))
        #expect(pretty.contains("node=Extract Entities"))
    }
}
