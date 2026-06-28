import Combine
import FicheroAPIClient
import Foundation
import OSLog

/// A bookmark node (node-model fold F4, #2591): a saved pointer to a target
/// document. Lightweight — the list view only needs the id + name; opening
/// resolves to the target via the backend.
struct BookmarkItem: Identifiable, Hashable {
    let id: String
    let name: String
}

/// Typed wrapper over the `/api/bookmarks` endpoints (#2755). All calls go
/// through the generated client — no hand-rolled URLSession. Degrades
/// gracefully: failures set `error` and leave `bookmarks` untouched.
@MainActor
final class BookmarkServiceGenerated: ObservableObject {
    private let client: FicheroClient
    @Published private(set) var bookmarks: [BookmarkItem] = []
    @Published var error: String?

    private let logger = Logger(subsystem: "app.fichero.fichero", category: "BookmarkService")

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// GET /api/bookmarks — bookmark nodes, optionally under a parent folder.
    func loadBookmarks(parentId: String? = nil) async {
        do {
            let response = try await client.api.listBookmarksApiBookmarksGet(
                .init(query: .init(parentId: parentId))
            )
            guard case .ok(let okResponse) = response else {
                error = "Could not load bookmarks"
                return
            }
            bookmarks = try okResponse.body.json.items.compactMap { doc in
                guard let id = doc.id else { return nil }
                return BookmarkItem(id: id, name: doc.name)
            }
            error = nil
        } catch {
            logger.warning("list bookmarks failed: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not load bookmarks"
        }
    }

    /// POST /api/bookmarks — bookmark `targetId` under `parentId`. Reloads on success.
    @discardableResult
    func createBookmark(targetId: String, name: String, parentId: String? = nil) async -> Bool {
        do {
            let request = Components.Schemas.BookmarkCreate(
                targetId: targetId,
                parentId: parentId,
                name: name
            )
            let response = try await client.api.createBookmarkApiBookmarksPost(.init(body: .json(request)))
            guard case .created = response else {
                error = "Could not create bookmark"
                return false
            }
            error = nil
            await loadBookmarks(parentId: parentId)
            return true
        } catch {
            logger.warning("create bookmark failed: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not create bookmark"
            return false
        }
    }

    /// GET /api/bookmarks/{id}/resolve — the target document id the bookmark points to.
    func resolveBookmark(id: String) async -> String? {
        do {
            let response = try await client.api.resolveBookmarkApiBookmarksBookmarkIdResolveGet(
                .init(path: .init(bookmarkId: id))
            )
            guard case .ok(let okResponse) = response else {
                error = "Could not resolve bookmark"
                return nil
            }
            return try okResponse.body.json.id
        } catch {
            logger.warning("resolve bookmark failed: \(error.localizedDescription, privacy: .public)")
            self.error = "Could not resolve bookmark"
            return nil
        }
    }
}
