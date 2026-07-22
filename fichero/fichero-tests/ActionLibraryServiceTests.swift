@testable import Fichero
import Foundation
import Testing

@Suite("ActionLibraryService bridges")
@MainActor
struct ActionLibraryServiceTests {

    private struct ActionPayload: Codable, Equatable {
        let name: String
        let enabled: Bool
        let count: Int
    }

    @Test("decodeModel preserves typed values through the generated-client bridge")
    func decodeModel() throws {
        let service = ActionLibraryService(client: .localhost)
        let input = ActionPayload(name: "Summarise", enabled: true, count: 3)

        let decoded = try service.decodeModel(from: input, as: ActionPayload.self)

        #expect(decoded == input)
    }

    @Test("objectContainer preserves nested JSON payloads for action graph requests")
    func objectContainer() throws {
        let service = ActionLibraryService(client: .localhost)
        let container = try service.objectContainer(from: [
            "kind": "workflow",
            "enabled": true,
            "nodes": [["id": "node-1", "label": "Extract"]]
        ])

        let value = try #require(container.value)
        #expect(value["kind"] as? String == "workflow")
        #expect(value["enabled"] as? Bool == true)
        let nodes = try #require(value["nodes"] as? [[String: any Sendable]])
        #expect(nodes.first?["id"] as? String == "node-1")
        #expect(nodes.first?["label"] as? String == "Extract")
    }

    @Test("objectContainer rejects values that JSON cannot represent")
    func objectContainerRejectsNonJSONValue() {
        let service = ActionLibraryService(client: .localhost)

        #expect(throws: Error.self) {
            try service.objectContainer(from: ["date": Date()])
        }
    }
}
