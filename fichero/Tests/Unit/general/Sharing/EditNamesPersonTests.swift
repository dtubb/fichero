import Foundation
import Testing

@testable import Fichero

/// `sharing.people.device-is-a-person` (#5735): the Inspector says who edited a document from another Mac, and on which.
struct EditNamesPersonTests {
    @Test func aChangeNamingAPersonAndADeviceReadsPersonOnDevice() {
        let editor = RemoteEditor(person: "maya", device: "Maya's Mac")
        #expect(editor?.words == "Edited by maya on Maya's Mac")
    }

    @Test func aChangeWithNoDeviceNamesThePersonAlone() {
        #expect(RemoteEditor(person: "maya", device: nil)?.words == "Edited by maya")
        #expect(RemoteEditor(person: "maya", device: "")?.words == "Edited by maya")
    }

    @Test func theHostsOwnEditNamesNoOneSoNothingIsRecorded() {
        #expect(RemoteEditor(person: nil, device: nil) == nil)
        #expect(RemoteEditor(person: "", device: "Mac") == nil)
    }

    private func event(_ type: String, person: String? = nil, device: String? = nil) throws -> ChangeEvent {
        var payload: [String: Any] = ["type": type, "document_ids": ["d1"], "actor": "workflow"]
        if let person { payload["person"] = person }
        if let device { payload["device"] = device }
        return try JSONDecoder().decode(ChangeEvent.self, from: JSONSerialization.data(withJSONObject: payload))
    }

    @MainActor @Test func theStoreKeepsTheLastRemoteEditorAndAHostEditClearsIt() throws {
        let store = DocumentStore(apiClient: APIClient())
        store.apply(try event("document.updated", person: "maya", device: "Maya's Mac"))
        #expect(store.remoteEditors["d1"]?.words == "Edited by maya on Maya's Mac")
        store.apply(try event("document.updated"))
        #expect(store.remoteEditors["d1"] == nil, "the host's own later edit names no one, so the old name goes")
    }

    @MainActor @Test func aDeleteDropsTheName() throws {
        let store = DocumentStore(apiClient: APIClient())
        store.apply(try event("document.updated", person: "maya"))
        store.apply(try event("document.deleted"))
        #expect(store.remoteEditors["d1"] == nil)
    }
}
