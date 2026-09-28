import Foundation
import Observation

/// Grant Access… for a library the engine refused as outside every location it may open (#5198).
///
/// The only thing that fixes that denial is the person choosing the library (or a folder holding it): the
/// app then holds a security-scoped grant it can hand to the engine. So: ask with the panel opened at the
/// library itself, bookmark the choice AND hand it to the engine before anything reads it (the ordered
/// grant, `FolderAccessManager.saveBookmarkIfDirectory`), then load again. The steps are injected so a
/// test drives them with the panel stubbed.
@MainActor
struct LibraryAccessGrant {
    /// What the panel is asked to show.
    struct Request: Equatable {
        /// The library itself: the panel opens in its folder with it selected.
        let directoryURL: URL
        let message: String
        let prompt: String

        /// A folder an import was refused (#5219): the same panel, worded for a folder, not a library.
        init(importURL: URL) {
            directoryURL = importURL
            message = "Fichero may not read \u{201C}\(importURL.lastPathComponent)\u{201D}: it is outside the folders "
                + "this Mac's engine may read. Choose it, or a folder holding it, to grant access."
            prompt = "Grant Access"
        }

        init(libraryURL: URL) {
            directoryURL = libraryURL
            message = "Fichero may not open \u{201C}\(libraryURL.deletingPathExtension().lastPathComponent)\u{201D}: it is "
                + "outside the folders this Mac's engine may open. Choose the library, or a folder holding it, "
                + "to grant access."
            prompt = "Grant Access"
        }
    }

    let choose: @MainActor (Request) async -> URL?
    let grant: @MainActor (URL) async throws -> Void
    let retry: @MainActor () async -> Void

    /// True when the person chose and the grant went through (then the load is retried); false when they
    /// cancelled -- nothing granted, nothing retried.
    @discardableResult
    func run(for libraryURL: URL) async throws -> Bool {
        guard let chosen = await choose(Request(libraryURL: libraryURL)) else { return false }
        try await grant(chosen)
        await retry()
        return true
    }
}

#if os(macOS)
extension LibraryAccessGrant {
    /// The app's: the panel, and the ordered grant (bookmark + hand to the engine) the existing
    /// library-open path uses.
    static func live(retry: @escaping @MainActor () async -> Void) -> LibraryAccessGrant {
        LibraryAccessGrant(
            choose: { request in await FolderAccessManager.shared.chooseForAccess(request) },
            grant: { url in try await FolderAccessManager.shared.saveBookmarkIfDirectory(url) },
            retry: retry
        )
    }
}
#endif

/// The path of the last import the engine refused as outside its allowed roots (#5219), for the Drop Failed
/// alerts to offer Grant Access… on. Set where the refusal is read (`ImportService.startFolderImport`), cleared
/// when the alert goes. One seam, because a drop's failure reaches the alerts as a message from a dozen sites.
@MainActor
@Observable
final class DropAccessRefusal {
    static let shared = DropAccessRefusal()
    var path: String?

    #if os(macOS)
    /// The panel at the refused folder, then the ordered grant. The drop is not replayed: its target and
    /// options belong to the drop, so the person drops again (the message says so).
    static func grantAccess(to path: String) async {
        let grant = LibraryAccessGrant(
            choose: { _ in
                await FolderAccessManager.shared.chooseForAccess(.init(importURL: URL(fileURLWithPath: path)))
            },
            grant: { url in try await FolderAccessManager.shared.saveBookmarkIfDirectory(url) },
            retry: {}
        )
        _ = try? await grant.run(for: URL(fileURLWithPath: path))
        shared.path = nil
    }
    #endif
}
