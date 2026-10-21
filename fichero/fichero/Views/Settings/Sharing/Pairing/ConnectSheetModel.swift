import Foundation

/// What the Connect to Another Mac sheet says and when Connect is available (`sharing.settings.connect-sheet`, #5928), apart from
/// the view so it is tested without a window.
enum ConnectSheetModel {
    static let pastePlaceholder = "https://…"
    static let codePlaceholder = "Code"

    /// "Searching…" in grey while the network is looked at and nothing is found yet; an empty list otherwise.
    static func nearbyStatus(searching: Bool, found: Int) -> String? { searching && found == 0 ? "Searching…" : nil }

    /// Where the code or link goes, said once: the picked Mac's address if one is picked, else the pasted link's host.
    static func connectsTo(pickedAddress: String?, pastedHost: String?) -> String? {
        (pickedAddress ?? pastedHost).map { "Connects to \($0)" }
    }

    /// Name and Password are asked only when the host asks for a person.
    static func asksForPerson(hostAskedForPerson: Bool) -> Bool { hostAskedForPerson }

    /// Connect needs what the route needs and is off while connecting. A picked Mac that pairs from its code needs the code;
    /// anything else needs the pasted link. When a person is asked for, both fields are needed.
    static func canConnect(codeRoute: Bool, code: String, link: String, isConnecting: Bool,
                           needsPerson: Bool = false, name: String = "", password: String = "") -> Bool {
        guard !isConnecting else { return false }
        let filled = !(codeRoute ? code : link).trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        guard needsPerson else { return filled }
        return filled && !name.trimmingCharacters(in: .whitespaces).isEmpty && !password.isEmpty
    }

    /// A tapped invite link opens the sheet with the link filled in, to be read and pressed by the person; nothing pairs by itself.
    nonisolated static func opensFor(pendingInvite: String?) -> Bool { !(pendingInvite ?? "").isEmpty }

    /// The sheet's button for the work in hand.
    static func connectTitle(isConnecting: Bool) -> String { isConnecting ? "Connecting…" : "Connect" }
}
