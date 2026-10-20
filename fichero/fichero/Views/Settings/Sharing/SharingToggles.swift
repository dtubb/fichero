import Foundation

/// The two switches on Settings › Sharing, and nothing else is asked
/// (sharing.two-toggles-wording, #3284). Both rows render from this.
enum SharingToggles {
    enum ID { case sharing, multiUser }

    struct Row {
        let id: ID
        let label: String
        let caption: String
    }

    static let all: [Row] = [
        Row(id: .sharing, label: "Sharing",
               caption: "Share Fichero on this Mac with other devices, the fichero command-line tool, and MCP clients."),
        Row(id: .multiUser, label: "Multi-user",
               caption: "Give other people their own accounts on this Mac's libraries."),
    ]

    /// What the People tab's "Invite a Person" section says while Multi-user is off: it names the switch where it is
    /// (Settings → Sharing → Devices), not a place it is not (#5917).
    static let multiUserOffHint =
        "Multi-user mode is off, so this project has one account and nobody to invite. "
        + "Turn on Multi-user in Settings → Sharing → Devices, and Fichero will restart its engine to apply it."

    static func caption(_ id: ID) -> String { all.first { $0.id == id }?.caption ?? "" }
}
