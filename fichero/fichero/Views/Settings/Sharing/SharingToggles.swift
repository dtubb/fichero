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

    static func caption(_ id: ID) -> String { all.first { $0.id == id }?.caption ?? "" }
}
