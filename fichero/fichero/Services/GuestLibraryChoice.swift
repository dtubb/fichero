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

    /// Why nothing is shown when the host could not be asked which libraries it serves, in words: not signed in (401), a host too
    /// old to list them (404 or 405), or not reachable. The guest drops its own local library for each of these: its own path is
    /// never what a remote host is asked about (## 688).
    static func problemWords(for error: Error) -> String {
        if let api = error as? APIError {
            switch api {
            case .httpError(let status, _) where status == 401 || status == 403:
                return "This device is not signed in to the Mac it is connected to. Pair it again from that Mac."
            case .httpError(let status, _) where status == 404 || status == 405:
                return "The Mac you are connected to needs a newer Fichero to share its projects."
            case .notFound:
                return "The Mac you are connected to needs a newer Fichero to share its projects."
            default:
                break
            }
        }
        return "The Mac you are connected to cannot be reached right now."
    }

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
