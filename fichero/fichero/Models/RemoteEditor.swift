import Foundation

/// Who last changed a document from another Mac (`sharing.names-on-edits`, #5735): the account and the paired device the
/// change event named. A host's own edit names no one, so nothing is recorded for it.
struct RemoteEditor: Equatable {
    let person: String
    let device: String?

    /// "Edited by maya on Maya's Mac", or "Edited by maya" when the device is not named.
    var words: String {
        guard let device, !device.isEmpty else { return "Edited by \(person)" }
        return "Edited by \(person) on \(device)"
    }

    /// From a change event's `person` and `device`; nil when the change names no person.
    init?(person: String?, device: String?) {
        guard let person, !person.isEmpty else { return nil }
        self.person = person
        self.device = device
    }
}
