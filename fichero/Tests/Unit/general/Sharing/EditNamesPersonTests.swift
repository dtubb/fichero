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
}
