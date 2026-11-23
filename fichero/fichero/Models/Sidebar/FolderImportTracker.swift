import Foundation
import Observation

/// The folders an import or a IIIF add is filling, for the sidebar (#7066, `import.folder-shows-at-once`). The engine
/// makes the destination folder and answers its id before it copies or fetches anything; the row itself arrives on the
/// change stream, in place, and this says what that row shows: a spinner while the import runs, and, if it failed, an
/// error mark with the reason. The finish event (the folder import's status, the IIIF job's state) clears it.
@MainActor
@Observable
final class FolderImportTracker {
    enum State: Equatable {
        case importing
        case failed(String)
    }

    /// One observable entry per folder, so a row that reads its own entry redraws only when its own import changes,
    /// not when any other folder's import begins or ends (#6547). The dictionary is not itself observed.
    @Observable
    final class Entry {
        fileprivate(set) var state: State?
    }

    @ObservationIgnored private var entries: [String: Entry] = [:]
    /// Folders whose row is to be revealed (their ancestors opened) once the row is known.
    private(set) var pendingReveal: Set<String> = []

    private func entry(_ folderId: String) -> Entry {
        if let existing = entries[folderId] { return existing }
        let made = Entry()
        entries[folderId] = made
        return made
    }

    /// The engine accepted the import: the folder row shows a spinner and is to be revealed.
    func begin(folderId: String) {
        entry(folderId).state = .importing
        pendingReveal.insert(folderId)
    }

    /// The import finished (or was cancelled, keeping what landed): the spinner goes.
    func finish(folderId: String) {
        entry(folderId).state = nil
        pendingReveal.remove(folderId)
    }

    /// The import failed: the row stays, marked, with the reason.
    func fail(folderId: String, reason: String) {
        entry(folderId).state = .failed(reason)
    }

    /// The person has seen the error: the mark goes.
    func dismissError(folderId: String) {
        if case .failed = entry(folderId).state { entry(folderId).state = nil }
    }

    func isImporting(_ folderId: String) -> Bool { entry(folderId).state == .importing }

    func error(for folderId: String) -> String? {
        if case .failed(let reason) = entry(folderId).state { return reason }
        return nil
    }

    /// The row was revealed: not asked again.
    func revealed(folderId: String) { pendingReveal.remove(folderId) }

    /// The ancestors to open to show `folderId`, nearest first; stops at a cycle.
    nonisolated static func ancestors(of folderId: String, parentOf: (String) -> String?) -> [String] {
        var chain: [String] = []
        var next = parentOf(folderId)
        while let id = next, id != folderId, !chain.contains(id) {
            chain.append(id)
            next = parentOf(id)
        }
        return chain
    }
}
