import FicheroAPIClient
import Foundation
import Observation

/// One thing in a project's Trash, as `GET /api/documents/trash` lists it
/// (`safety.trash.lists-what-and-why`): each thing deleted once, with what went with it, when,
/// by whom, where it was, and why ("Deleted by ana", "Moved to Istmina on 10 Oct 2026"). The
/// words are the engine's; the app only lays them out.
struct TrashEntry: Identifiable, Equatable {
    let id: String
    let name: String
    let isFolder: Bool
    let deletedAt: Date?
    let deletedBy: String?
    /// How many things inside it were deleted with it.
    let itemCount: Int
    /// Where it was, in words ("Box 3 / Letters", "A folder now gone").
    let fromWhere: String
    /// Why it is here, in words.
    let why: String
    let wasMoved: Bool

    init(_ item: Components.Schemas.TrashItem) {
        id = item.id
        name = item.name
        isFolder = item.docType == .folder
        deletedAt = item.deletedAt
        deletedBy = item.deletedBy
        itemCount = item.itemCount
        fromWhere = item.fromWhere
        why = item.why
        wasMoved = item.reason.rawValue == "moved"
    }

    init(
        id: String, name: String, isFolder: Bool = false, deletedAt: Date? = nil, deletedBy: String? = nil,
        itemCount: Int = 0, fromWhere: String, why: String, wasMoved: Bool = false
    ) {
        self.id = id
        self.name = name
        self.isFolder = isFolder
        self.deletedAt = deletedAt
        self.deletedBy = deletedBy
        self.itemCount = itemCount
        self.fromWhere = fromWhere
        self.why = why
        self.wasMoved = wasMoved
    }

    /// "40 items inside", or nil for a thing with nothing inside.
    var contentsText: String? {
        switch itemCount {
        case 0: return nil
        case 1: return "1 item inside"
        default: return "\(itemCount) items inside"
        }
    }

    /// "From Box 3 / Letters · 10 Oct 2026 at 14:02".
    var whereAndWhenText: String {
        guard let deletedAt else { return "From \(fromWhere)" }
        return "From \(fromWhere) · \(deletedAt.formatted(date: .abbreviated, time: .shortened))"
    }
}

/// What Empty Trash will remove, asked before it runs (`safety.trash.empty-says-what-will-go`,
/// `safety.trash.empty-names-moved-items`): the engine's question and one sentence per project a
/// move sent items from.
struct EmptyTrashQuestion: Equatable {
    let question: String
    let movedSentences: [String]
    let itemCount: Int

    /// The alert's message: the moved-items sentences, then that it cannot be undone.
    var message: String {
        (movedSentences + ["This cannot be undone."]).joined(separator: "\n\n")
    }
}

/// A project's Trash (#2077, #5243, `safety.trash.one-per-project`): the list the Trash row opens,
/// Put Back and Empty Trash. One per project (on `LibraryReference`), read through that project's
/// client, so each project's Trash lists only its own deleted items.
///
/// Updates one entry at a time (no wholesale re-render): Put Back removes that entry in place, and
/// a reload after a `document.*` change event merges by id: gone entries leave, new ones are
/// inserted where the engine lists them, changed ones are replaced in place.
@MainActor
@Observable
final class TrashStore: ChangeEventConsumer {
    private(set) var entries: [TrashEntry] = []
    private(set) var hasLoaded = false
    /// The engine's last sentence about what happened ("Put back in Sources: its folder is in the
    /// Trash."); the pane shows it until the next action.
    private(set) var notice: String?
    private(set) var errorMessage: String?
    /// Set while Empty Trash is asking; the pane presents it, and nothing is removed until confirmed.
    var emptyQuestion: EmptyTrashQuestion?
    private(set) var isWorking = false

    @ObservationIgnored private let client: FicheroClient
    @ObservationIgnored private let reloadDebouncer: ReloadDebouncer

    init(client: FicheroClient, entries: [TrashEntry] = [], reloadDebouncer: ReloadDebouncer = ReloadDebouncer()) {
        self.client = client
        self.entries = entries
        self.reloadDebouncer = reloadDebouncer
    }

    var isEmpty: Bool { entries.isEmpty }

    /// Read the project's Trash and merge it in, one entry at a time.
    func load() async {
        do {
            switch try await client.api.listDeletedDocumentsApiDocumentsTrashGet(query: .init()) {
            case .ok(let success):
                merge(try success.body.json.items.map(TrashEntry.init))
                hasLoaded = true
                errorMessage = nil
            case .unprocessableContent:
                errorMessage = "Could not read the Trash."
            case .undocumented(let code, _):
                errorMessage = "Could not read the Trash (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read the Trash: \(error.localizedDescription)"
        }
    }

    /// Bring `entries` to `fresh` by id, touching only what changed.
    func merge(_ fresh: [TrashEntry]) {
        let freshIds = Set(fresh.map(\.id))
        entries.removeAll { !freshIds.contains($0.id) }
        for (index, entry) in fresh.enumerated() {
            if let current = entries.firstIndex(where: { $0.id == entry.id }) {
                if entries[current] != entry { entries[current] = entry }
                if current != index, index < entries.count {
                    let moved = entries.remove(at: current)
                    entries.insert(moved, at: min(index, entries.count))
                }
            } else {
                entries.insert(entry, at: min(index, entries.count))
            }
        }
    }

    /// Put Back (`safety.trash.put-back`): each item returns to its old folder, or to Sources when
    /// that folder is gone or in the Trash. Each put-back entry leaves the list in place; `notice`
    /// holds the engine's sentence about where the last one went.
    @discardableResult
    func putBack(_ ids: [String]) async -> String? {
        isWorking = true
        defer { isWorking = false }
        var said: [String] = []
        for id in ids {
            do {
                switch try await client.api.restoreDocumentApiDocumentsDocIdRestorePost(.init(path: .init(docId: id))) {
                case .ok(let success):
                    said.append(try success.body.json.message)
                    entries.removeAll { $0.id == id }
                case .unprocessableContent:
                    errorMessage = "Could not put that back."
                case .undocumented(let code, _):
                    errorMessage = "Could not put that back (HTTP \(code))."
                }
            } catch {
                if error.isCancellationError { break }
                errorMessage = "Could not put that back: \(error.localizedDescription)"
            }
        }
        if !said.isEmpty {
            notice = said.count == 1 ? said[0] : "Put back \(said.count) items. " + (said.last ?? "")
        }
        return said.last
    }

    /// Empty Trash…, first half: read what would go and ask (`emptyQuestion`). Nothing is removed.
    func askToEmpty() async {
        do {
            switch try await client.api.previewEmptyTrashApiDocumentsTrashEmptyGet() {
            case .ok(let success):
                let preview = try success.body.json
                emptyQuestion = EmptyTrashQuestion(
                    question: preview.sentence,
                    movedSentences: (preview.moved ?? []).map(\.sentence),
                    itemCount: preview.items
                )
                errorMessage = nil
            case .undocumented(let code, _):
                errorMessage = "Could not read what is in the Trash (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read what is in the Trash: \(error.localizedDescription)"
        }
    }

    /// Empty Trash…, second half, after the person said yes: one recorded step that cannot be undone.
    func confirmEmpty() async {
        emptyQuestion = nil
        isWorking = true
        defer { isWorking = false }
        do {
            switch try await client.api.emptyTheTrashApiDocumentsTrashEmptyPost() {
            case .ok(let success):
                let result = try success.body.json
                entries.removeAll()
                notice = result.documents == 1 ? "Deleted 1 item for good." : "Deleted \(result.documents) items for good."
                errorMessage = nil
            case .unprocessableContent:
                errorMessage = "Could not empty the Trash."
            case .undocumented(let code, _):
                errorMessage = code == 503
                    ? "The Trash was not emptied: a snapshot could not be made first."
                    : "Could not empty the Trash (HTTP \(code))."
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not empty the Trash: \(error.localizedDescription)"
        }
    }

    func cancelEmpty() { emptyQuestion = nil }

    // MARK: - ChangeEventConsumer

    nonisolated var changeDomains: Set<String> { ["document"] }

    func apply(_ event: ChangeEvent) {
        reloadDebouncer.schedule { [weak self] in
            await self?.load()
        }
    }

    func resync() async {
        await load()
    }
}
