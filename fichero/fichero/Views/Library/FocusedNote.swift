import FicheroAPIClient
import Foundation
import Observation

/// One note row in a List + detail surface.
///
/// `Components.Schemas.Note.id` is optional, so this wrapper gives the list a
/// stable identity and exposes a few compact display fields for the summary
/// rows.
struct NoteSelectionItem: Identifiable, Hashable {
    let note: NoteItem

    var id: String {
        if let noteId = note.id, !noteId.isEmpty { return noteId }
        return [
            note.title ?? "",
            note.body ?? "",
            note.kind?.rawValue ?? "",
            note.updatedAt?.timeIntervalSince1970.description ?? ""
        ].joined(separator: "|")
    }

    var title: String {
        if let title = note.title, !title.isEmpty { return title }
        if let body = note.body, !body.isEmpty { return String(body.prefix(90)) }
        return "Untitled note"
    }

    var bodyPreview: String {
        guard let body = note.body, !body.isEmpty else { return "No body text" }
        if body.count <= 140 { return body }
        return String(body.prefix(140)) + "…"
    }

    var kindLabel: String {
        (note.kind?.rawValue ?? "zettel").capitalized
    }

    var scopeLabel: String? {
        if note.folderId?.isEmpty == false { return "Folder" }
        if note.pageId?.isEmpty == false { return "Page" }
        return nil
    }

    var tagsLabel: String? {
        let tags = note.tags ?? []
        guard !tags.isEmpty else { return nil }
        return tags.prefix(3).map { "#\($0)" }.joined(separator: " ")
    }

    var updatedLabel: String? {
        guard let updatedAt = note.updatedAt else { return nil }
        return updatedAt.formatted(date: .abbreviated, time: .shortened)
    }

    static func == (lhs: NoteSelectionItem, rhs: NoteSelectionItem) -> Bool { lhs.id == rhs.id }
    func hash(into hasher: inout Hasher) { hasher.combine(id) }
}

/// Shared selection holder for the note List + detail.
@Observable
@MainActor
final class FocusedNote {
    static let shared = FocusedNote()

    var id: String?
    private(set) var item: NoteSelectionItem?
    var documentName: String?

    init() {}

    func select(_ id: String?, in items: [NoteSelectionItem]) {
        self.id = id
        resolve(in: items)
    }

    func resolve(in items: [NoteSelectionItem]) {
        item = id.flatMap { selectedId in items.first { $0.id == selectedId } }
    }

    func clear() {
        id = nil
        item = nil
    }
}
