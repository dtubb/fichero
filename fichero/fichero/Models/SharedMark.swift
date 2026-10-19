import Foundation

/// The small "shared" marks: on a guest's project row (`sharing.sidebar.guest-row`) and on the host's own
/// project while Sharing is on (`sharing.sidebar.host-mark`, #5738).
nonisolated enum SharedMark {
    static let symbol = "person.2"
    static let hostHelp = "Shared with other devices"

    /// The host's mark: this Mac's own project (a local host) while Sharing is on.
    static func showsOnHost(hostingEnabled: Bool, isLocal: Bool) -> Bool { hostingEnabled && isLocal }
}
