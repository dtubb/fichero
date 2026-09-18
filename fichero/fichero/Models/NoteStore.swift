import Foundation
import Observation
import OSLog

/// Observable domain store for notes (#1882, mirrors `EntityStore`).
///
/// The single endpoint accessor for the note list a view renders. A view never
/// calls `NoteService` directly: it observes `notes` and dispatches the named
/// actions below. Each action performs the typed write and then refreshes the
/// current scope — today via an explicit reload, and via `apply(_:)` once the
/// per-library change-stream starts emitting `note.*` events. Swapping reload
/// for push is then a no-op at every call site.
///
/// Notes are loaded against one of several scopes (whichever the view set last):
///   • a *document* scope — inspector notes, backed by `?linked_document_id=…`
///   • a *page* scope — page-anchored notes, backed by `?page_id=…`
///   • a *folder* scope — folder-level notes, backed by `?folder_id=…`
///   • an *entity* scope — entity bio/summary notes, backed by `?linked_entity_id=…`
///   • an *all* scope — standalone notes browser, backed by kind/tag/query filters
///
/// One instance per library (registered on `LibraryReference`), shared across
/// that library's windows.
@MainActor
@Observable
final class NoteStore: ObservableDomainStore {
    enum Scope: Equatable {
        case none
        case document(String)
        case page(String)
        case folder(String)
        case entity(String)
        case all(kind: String, tag: String, query: String)
    }

    /// Whether `note` belongs in the CURRENTLY-VISIBLE `scope` (#4824) — used
    /// by the mutators below to decide whether a just-created/updated note
    /// should be spliced into `notes` in place, or left out because it
    /// belongs to a different scope than the one on screen. Pure + tested.
    static func belongs(_ note: NoteItem, to scope: Scope) -> Bool {
        switch scope {
        case .none:
            return false
        case .document(let id):
            return (note.linkedDocumentIds ?? []).contains(id)
        case .page(let id):
            return note.pageId == id
        case .folder(let id):
            return note.folderId == id
        case .entity(let id):
            return (note.linkedEntityIds ?? []).contains(id)
        case .all(let kind, let tag, let query):
            // A full-text `query` (or a `tag`) can't be re-evaluated
            // client-side from the returned item alone — skip the splice
            // rather than risk showing a note that doesn't actually match.
            // A plain "all notes of this kind" browse (empty tag/query) is
            // the one case that's safe to check.
            guard query.isEmpty, tag.isEmpty else { return false }
            return kind.isEmpty || note.kind?.rawValue == kind
        }
    }

    // ─── Published domain state (views read these directly) ───
    private(set) var notes: [NoteItem] = []
    private(set) var isLoading = false
    private(set) var loadError: String?
    private(set) var scope: Scope = .none

    /// Monotonic counter bumped on every applied `note.*` change event.
    /// Views that keep their own differently-scoped note load observe this
    /// token and resync when it changes. Mirrors `ClaimStore.changeToken`.
    private(set) var changeToken: Int = 0

    // ─── Transport: the EXISTING NoteService wrapper, unchanged ───
    private let noteService: NoteService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "NoteStore")

    init(noteService: NoteService) {
        self.noteService = noteService
    }

    // MARK: - Load (the store, not the view, owns fetching)

    func loadNotes(forDocument documentId: String, force: Bool = false) async {
        if !force, scope == .document(documentId), !notes.isEmpty { return }
        await load(.document(documentId)) { await self.noteService.load(linkedDocumentId: documentId) }
    }

    func loadNotes(forPage pageId: String, force: Bool = false) async {
        if !force, scope == .page(pageId), !notes.isEmpty { return }
        await load(.page(pageId)) { await self.noteService.load(pageId: pageId) }
    }

    func loadNotes(forFolder folderId: String, force: Bool = false) async {
        if !force, scope == .folder(folderId), !notes.isEmpty { return }
        await load(.folder(folderId)) { await self.noteService.load(folderId: folderId) }
    }

    func loadNotes(forEntity entityId: String, force: Bool = false) async {
        if !force, scope == .entity(entityId), !notes.isEmpty { return }
        await load(.entity(entityId)) { await self.noteService.load(linkedEntityId: entityId) }
    }

    /// Load all notes, optionally filtered. Powers the standalone notes browser.
    func loadAll(kind: String = "", tag: String = "", query: String = "", force: Bool = false) async {
        let newScope = Scope.all(kind: kind, tag: tag, query: query)
        if !force, scope == newScope, !notes.isEmpty { return }
        await load(newScope) {
            await self.noteService.loadAll(kind: kind, tag: tag, query: query)
        }
    }

    private func load(_ newScope: Scope, _ fetch: () async -> Void) async {
        isLoading = true
        loadError = nil
        defer { isLoading = false }
        await fetch()
        notes = noteService.notes
        loadError = noteService.error
        scope = newScope
        log.debug("Loaded \(self.notes.count, privacy: .public) notes")
    }

    /// Re-fetch the current scope (post-mutation / reconnect resync).
    func reload() async {
        switch scope {
        case .none: return
        case .document(let id): await loadNotes(forDocument: id, force: true)
        case .page(let id): await loadNotes(forPage: id, force: true)
        case .folder(let id): await loadNotes(forFolder: id, force: true)
        case .entity(let id): await loadNotes(forEntity: id, force: true)
        case .all(let kind, let tag, let query): await loadAll(kind: kind, tag: tag, query: query, force: true)
        }
    }

    // MARK: - Named actions (map 1:1 to the audited action layer, #1848)

    /// #4824: the service already maintains its own correctly-spliced
    /// `NoteService.notes` — these mutators used to throw that away with an
    /// `await reload()` (a full server re-fetch) right after. They now splice
    /// the STORE's own `notes` directly from the returned item, gated by
    /// `belongs(_:to:)` so a note created/edited for a DIFFERENT scope than
    /// the one on screen doesn't leak into the current list.
    @discardableResult
    func createForDocument(_ documentId: String, body: String) async throws -> NoteItem {
        let note = try await noteService.create(body: body, linkedDocumentId: documentId)
        if Self.belongs(note, to: scope) { notes.insert(note, at: 0) }
        return note
    }

    @discardableResult
    func createForPage(_ pageId: String, body: String) async throws -> NoteItem {
        let note = try await noteService.create(body: body, pageId: pageId)
        if Self.belongs(note, to: scope) { notes.insert(note, at: 0) }
        return note
    }

    @discardableResult
    func createForFolder(_ folderId: String, body: String) async throws -> NoteItem {
        let note = try await noteService.create(body: body, folderId: folderId)
        if Self.belongs(note, to: scope) { notes.insert(note, at: 0) }
        return note
    }

    @discardableResult
    func createForEntity(_ entityId: String, body: String, kind: String = "reference") async throws -> NoteItem {
        let note = try await noteService.create(body: body, linkedEntityId: entityId, kind: kind)
        if Self.belongs(note, to: scope) { notes.insert(note, at: 0) }
        return note
    }

    @discardableResult
    func createFree(body: String, kind: String) async throws -> NoteItem {
        let note = try await noteService.createFree(body: body, kind: kind)
        if Self.belongs(note, to: scope) { notes.insert(note, at: 0) }
        return note
    }

    /// An edit can also move a note OUT of the visible scope (e.g. a kind
    /// change on a `.all(kind:...)` browse) — `belongs` decides whether the
    /// row stays, updates in place, or drops out of the current list.
    @discardableResult
    func update(noteId: String, body: String) async throws -> NoteItem {
        let updated = try await noteService.update(noteId: noteId, body: body)
        if let idx = notes.firstIndex(where: { $0.id == noteId }) {
            if Self.belongs(updated, to: scope) {
                notes[idx] = updated
            } else {
                notes.remove(at: idx)
            }
        } else if Self.belongs(updated, to: scope) {
            notes.insert(updated, at: 0)
        }
        return updated
    }

    func delete(noteId: String) async throws {
        try await noteService.delete(noteId: noteId)
        notes.removeAll { $0.id == noteId }
    }

    // MARK: - Links (#1433 — note↔note relations, read-through to the service)

    /// Backlinks + forward links for one note. The store is the single accessor;
    /// views observe/dispatch here rather than calling `NoteService` directly.
    func links(for noteId: String) async throws -> NoteLinks {
        async let backlinks = noteService.backlinks(noteId: noteId)
        async let forward = noteService.forwardLinks(noteId: noteId)
        return NoteLinks(backlinks: try await backlinks, forward: try await forward)
    }

    // MARK: - ChangeEventConsumer (called by LibraryChangeStream, NOT by views)

    nonisolated var changeDomain: String { "note" }

    func apply(_ event: ChangeEvent) {
        changeToken &+= 1
        switch event.verb {
        case "created", "updated", "deleted":
            scheduleReload()
        default:
            break
        }
    }

    /// Holds the shared 300ms trailing-reload debouncer (#1973). `scheduleReload()`
    /// (called above for create/update/delete) and `resync()` are provided by the
    /// `ObservableDomainStore` extension — no per-store copies.
    let reloadDebouncer = ReloadDebouncer()
}
