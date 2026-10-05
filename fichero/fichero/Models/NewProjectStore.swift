import FicheroAPIClient
import Foundation
import Observation

/// Setup's first screen, Where it lives (section 7b screen 1, #5482; ruled 2026-10-05): the
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

    var name = "My Project"
    var place: Place = .insideFichero
    private(set) var isCreating = false
    private(set) var errorMessage: String?
    /// The project Continue made; setup reads and saves through its client from then on.
    private(set) var created: LibraryManager.LibraryReference?

    static let cannotWrite = "Fichero can't write to that folder. Choose another."

    private let libraryManager: LibraryManager
    /// Has the engine open the new project (`POST /api/library`). A seam so a test can stand in
    /// for the engine; the app's is the project's own `initializeLibrary`.
    private let openInEngine: (LibraryManager.LibraryReference) async throws -> Void

    init(libraryManager: LibraryManager,
         openInEngine: ((LibraryManager.LibraryReference) async throws -> Void)? = nil) {
        self.libraryManager = libraryManager
        self.openInEngine = openInEngine ?? { try await $0.apiClient.initializeLibrary(path: $0.url.path) }
    }

    /// The name as a file name: what a folder cannot hold is replaced, and an empty name is
    /// "My Project".
    var fileName: String {
        let cleaned = name.trimmingCharacters(in: .whitespacesAndNewlines)
            .replacingOccurrences(of: "/", with: "-")
            .replacingOccurrences(of: ":", with: "-")
        return cleaned.isEmpty ? "My Project" : cleaned
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
            try await openInEngine(project)
            created = project
            return project
        } catch {
            if error.isCancellationError { return nil }
            errorMessage = "\(Self.cannotWrite) (\(error.localizedDescription))"
            return nil
        }
    }
}
