import Foundation

/// A shared project whose host turned Sharing off (`sharing.sidebar.off-greys-row`, #5739): the guest's
/// sidebar keeps the row, greyed, with one sentence, until the person chooses Forget.
struct HostGoneRow: Identifiable, Equatable {
    let id: UUID
    let name: String
    let host: String

    var sentence: String {
        host.isEmpty ? "Not available: sharing is off on the host" : "Not available: sharing is off on \(host)"
    }
}
