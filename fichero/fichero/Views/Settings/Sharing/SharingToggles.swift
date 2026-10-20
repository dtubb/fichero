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

    /// Where the Sharing switches live: ONE constant, so moving them is one edit (#5917).
    static let location = "Settings → Sharing → Advanced"

    /// The switch's name, found by its id (not by its place in the list).
    static func label(_ id: ID) -> String { all.first { $0.id == id }?.label ?? "" }

    /// What the People tab's "Invite a Person" section says while Multi-user is off: it names the switch where it is,
    /// not a place it is not. It promises nothing about restarting: Multi-user stays off until the owner has a
    /// password (#5908), so "turn it on" can be refused.
    static var multiUserOffHint: String {
        "Multi-user mode is off, so this project has one account and nobody to invite. "
            + "Turn on \(label(.multiUser)) in \(location)."
    }

    static func caption(_ id: ID) -> String { all.first { $0.id == id }?.caption ?? "" }
}
