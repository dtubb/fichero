import Foundation

/// Which library a paired guest addresses on its host (`sharing.guest-addresses-the-hosts-library`, #5965): always one the HOST
/// serves, never the guest's own local path. Pure, so the choice is tested without an engine.
enum GuestLibraryChoice {
    enum Choice: Equatable {
        case path(String)
        case none
    }

    /// What the guest says when the host serves no library for it, in words.
    static let noneServedWords = "The Mac you are connected to has no project shared with this device yet."

    /// The pairing's library path if it carried one; else, from the libraries the host says this credential may open (the
    /// engine lists them most recently used first): the only one, else the host's global one, else the first.
    static func choose(paired: String, accessible: [String]) -> Choice {
        let paired = paired.trimmingCharacters(in: .whitespacesAndNewlines)
        if !paired.isEmpty { return .path(paired) }
        let paths = accessible.map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        if paths.count == 1 { return .path(paths[0]) }
        if let global = paths.first(where: { URL(fileURLWithPath: $0).lastPathComponent == "global.fichero" }) {
            return .path(global)
        }
        return paths.first.map(Choice.path) ?? .none
    }
}
