import FicheroAPIClient
import Foundation
import Observation

/// Setup's first step, Your project (section 7b step 1, #5482; ruled 2026-10-05): the
/// project's name and one of two places, **Inside Fichero** (the default: the app's own data
/// folder, managed for the person) or a folder the person chooses. Continue makes the project
/// there through the one create path (`LibraryManager.createProject(at:)`) and has the engine
/// open it (`POST /api/library`), so every setup call after this one goes through THAT
/// project's client (#5477). A place that cannot be written is refused here, in words.
@MainActor
@Observable
final class NewProjectStore {
    enum Place: Equatable {
        case insideFichero
        case chosen(URL)
    }

    var name = "Untitled Project"
    /// The model the project searches with, chosen here and kept (`search.embedding.chosen-at-project-creation`);
    /// changing it later is a re-embed run (`EmbeddingChangeStore`).
    var embeddingModel = EmbeddingModelChoice.defaultModel
    /// The models the menu offers: the engine's list with its one lines once read (`GET /api/search/embedding/models`,
    /// library-free, #6144), the built-in one until then or when the engine cannot be reached.
    private(set) var embeddingChoices = EmbeddingModelChoice.all
    var place: Place = .insideFichero
    private(set) var isCreating = false
    private(set) var errorMessage: String?
    /// The project Continue made; setup reads and saves through its client from then on.
    private(set) var created: LibraryManager.LibraryReference?

    static let cannotWrite = "Fichero can't write to that folder. Choose another."

    private let libraryManager: LibraryManager
    /// Has the engine open the new project (`POST /api/library`). A seam so a test can stand in
    /// for the engine; without one it is the project's own `initializeLibrary`, with the chosen search model.
    private let openInEngine: ((LibraryManager.LibraryReference) async throws -> Void)?

    /// Moves the package to the Trash (recoverable, never an unlink). A seam for the test.
    private let trash: (URL) throws -> Void

    /// Hands the engine the save panel's grant for a chosen folder before it is asked to open the project there
    /// (#6255: a project outside the app's container was refused, 403 failed_check=roots). A seam for the test.
    private let grantFolder: (URL) async throws -> Void

    init(libraryManager: LibraryManager,
         openInEngine: ((LibraryManager.LibraryReference) async throws -> Void)? = nil,
         trash: ((URL) throws -> Void)? = nil,
         grantFolder: ((URL) async throws -> Void)? = nil) {
        self.libraryManager = libraryManager
        self.trash = trash ?? { try LibraryManager.trashPackage(at: $0) }
        self.openInEngine = openInEngine
        self.grantFolder = grantFolder ?? { try await FolderAccessManager.shared.saveBookmarkIfDirectory($0) }
    }

    /// Read the engine's list of search models; a choice it no longer offers falls back to the first (the recommended).
    func loadEmbeddingChoices(client: FicheroClient) async {
        guard let listed = await EmbeddingModelChoice.fetch(client: client) else { return }
        embeddingChoices = listed
        if !listed.contains(where: { $0.model == embeddingModel }), let first = listed.first { embeddingModel = first.model }
    }

    /// The name as a file name: what a folder cannot hold is replaced, and an empty name is
    /// "Untitled Project".
    var fileName: String {
        let cleaned = name.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "/", with: "-")
            .replacingOccurrences(of: ":", with: "-")
        return cleaned.isEmpty ? "Untitled Project" : cleaned
    }

    /// The folder the project goes in.
    var folder: URL? {
        switch place {
        case .insideFichero: libraryManager.insideFicheroDirectory
        case .chosen(let folder): folder
        }
    }

    /// Where the project will be made: `<folder>/<name>.fichero`, its name NFC-normalized so no
    /// decomposed-accent twin of the path is ever written (#3076: "Chocó").
    var projectURL: URL? {
        folder?.appendingPathComponent(fileName).appendingPathExtension("fichero").nfcNormalizedLastComponent
    }

    /// Make the project (once: a second Continue keeps the first). Returns it, or nil with the
    /// reason on screen and the person still on this screen.
    func create() async -> LibraryManager.LibraryReference? {
        if let created { return created }
        errorMessage = nil
        guard let url = projectURL, let folder else {
            errorMessage = Self.cannotWrite
            return nil
        }
        guard !FileManager.default.fileExists(atPath: url.path) else {
            errorMessage = "There is already a project called “\(fileName)” there. Choose another name."
            return nil
        }
        // A folder the person chose is granted for this use (the sandboxed builds); Inside
        // Fichero is the app's own and needs no grant.
        let scoped = folder.startAccessingSecurityScopedResource()
        defer { if scoped { folder.stopAccessingSecurityScopedResource() } }
        // Writable is decided by trying, never by guessing from the path.
        do {
            try FileManager.default.createDirectory(at: folder, withIntermediateDirectories: true)
        } catch {
            errorMessage = Self.cannotWrite
            return nil
        }
        guard FileManager.default.isWritableFile(atPath: folder.path) else {
            errorMessage = Self.cannotWrite
            return nil
        }
        isCreating = true
        defer { isCreating = false }
        do {
            let project = try libraryManager.createProject(at: url)
            // After createProject (it gives the grants an engine client), before the engine opens the package.
            if case .chosen = place { try await grantFolder(folder) }
            if let openInEngine {
                try await openInEngine(project)
            } else {
                try await project.apiClient.initializeLibrary(path: project.url.path, embeddingModel: embeddingModel)
            }
            created = project
            return project
        } catch {
            if error.isCancellationError { return nil }
            errorMessage = "\(Self.cannotWrite) (\(error.localizedDescription))"
            return nil
        }
    }

    /// Cancel on a new project's Set Up: close the project this store made and move its package to the Trash
    /// (#6117). Deletes only `created`, never a project the store did not make. Returns whether it deleted one.
    @discardableResult
    func discard() -> Bool {
        guard let project = created else { return false }
        let url = project.url
        created = nil
        do {
            try LibraryManager.closeAndTrash(url, close: { libraryManager.closeAndUnregisterLibrary(project.id) },
                                             trash: trash)
        } catch {
            errorMessage = "The project is closed, but its folder could not be moved to the Trash: \(error.localizedDescription)"
            return false
        }
        return true
    }
}
