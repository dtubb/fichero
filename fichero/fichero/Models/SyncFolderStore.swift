import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime

/// A project's synced folders (`source/synced-folder.md`; #4952, #5480): the folders on the
/// engine's disk the project is tied to, what each holds, and its intake (files changed in the
/// folder, waiting to come in as passes). The app half of `/api/sync-folders`: setup's Index ties
/// the folder here (`source.onboard.index-ties-the-folder`), and the folder's Inspector reads its
/// state here (`source.sync.status-in-inspector`). Through the generated client only.
///
/// One per project (`LibraryReference.syncFolderStore`), over that project's client. Each change
/// splices the one folder it touched; only `load()` replaces the list.
@MainActor
@Observable
final class SyncFolderStore {
    /// The project's synced folders as the engine last reported them (`GET /api/sync-folders`).
    private(set) var folders: [Components.Schemas.SyncFolderStatus] = []
    /// Each folder's intake as last read: on or off, and what it would bring in, by format.
    private(set) var intakeStates: [String: Components.Schemas.IntakeState] = [:]
    private(set) var hasLoaded = false
    var errorMessage: String?

    private let client: FicheroClient

    init(client: FicheroClient) {
        self.client = client
    }

    // MARK: Reading

    /// Read the project's synced folders. The list's identity is the engine's (a resync), so
    /// this is the one place it is replaced whole.
    func load() async {
        errorMessage = nil
        do {
            folders = try await fetchFolders()
            hasLoaded = true
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read this project's synced folders: \(error.localizedDescription)"
        }
    }

    /// The synced folder at `path`, if the project is tied to one there. Paths are compared as
    /// the engine records them (it resolves symlinks: `/var` is `/private/var` on a Mac), so a
    /// folder imported by the path the person picked still finds its synced folder.
    func folder(atPath path: String) -> Components.Schemas.SyncFolderStatus? {
        let wanted = Self.canonical(path)
        return folders.first { Self.canonical($0.path) == wanted }
    }

    /// What intake would bring in for a folder now, and whether it is on
    /// (`GET /api/sync-folders/{id}/intake`): the preview shown before Take In.
    func fetchIntake(_ folderId: String) async {
        do {
            switch try await client.api.getIntakeApiSyncFoldersFolderIdIntakeGet(path: .init(folderId: folderId)) {
            case .ok(let success):
                intakeStates[folderId] = try success.body.json
            case .unprocessableContent:
                errorMessage = "The engine did not understand which folder to read."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not read what this folder would take in (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not read what this folder would take in: \(error.localizedDescription)"
        }
    }

    // MARK: Changing (each splices the one folder it touched)

    /// Tie the project to the folder at `path` (`POST /api/sync-folders`) unless it already is.
    /// An Index import adopts its folder in the engine as it reads it, so the folder is usually
    /// there already, kept in its own layout; posting again would make a second synced folder
    /// writing Fichero's own layout into the person's folder. Returns the tied folder, with its
    /// intake read, or nil with `errorMessage` set.
    @discardableResult
    func tie(path: String, formats: [String] = ["pagexml"]) async -> Components.Schemas.SyncFolderStatus? {
        errorMessage = nil
        do {
            let current = try await fetchFolders()
            var tied = current.first { Self.canonical($0.path) == Self.canonical(path) }
            if tied == nil {
                switch try await client.api.tieFolderApiSyncFoldersPost(body: .json(.init(path: path, formats: formats))) {
                case .ok(let success):
                    let id = try success.body.json.id
                    tied = try await fetchFolders().first { $0.id == id }
                case .unprocessableContent:
                    errorMessage = "The engine would not tie \(path)."
                    return nil
                case .undocumented(let code, let body):
                    errorMessage = await EngineErrorDetail.message(from: body)
                        ?? "Could not tie \(path) (HTTP \(code))"
                    return nil
                }
            }
            guard let tied else {
                errorMessage = "The engine tied \(path) but does not list it."
                return nil
            }
            splice(tied)
            await fetchIntake(tied.id)
            return tied
        } catch {
            if error.isCancellationError { return nil }
            errorMessage = await Self.engineWords(error) ?? "Could not tie \(path): \(error.localizedDescription)"
            return nil
        }
    }

    /// Take In (`on: true`) or Leave (`on: false`) what changed in the folder
    /// (`PUT /api/sync-folders/{id}/intake`). Taken in, each changed file comes in as a new pass
    /// ("edited outside Fichero"), overwriting nothing. Left, nothing comes in.
    @discardableResult
    func setIntake(_ folderId: String, on isOn: Bool) async -> Bool {
        errorMessage = nil
        do {
            switch try await client.api.putIntakeApiSyncFoldersFolderIdIntakePut(
                path: .init(folderId: folderId), body: .json(.init(on: isOn))
            ) {
            case .ok(let success):
                let state = try success.body.json
                intakeStates[folderId] = state
                if let index = folders.firstIndex(where: { $0.id == folderId }) {
                    folders[index].intake = state.on
                }
                return true
            case .unprocessableContent:
                errorMessage = "The engine did not understand the change to this folder's intake."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not change this folder's intake (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = "Could not change this folder's intake: \(error.localizedDescription)"
        }
        return false
    }

    /// Untie a folder (`DELETE /api/sync-folders/{id}`): writing and intake stop; its files stay
    /// on disk (`source.sync.untie-leaves-files`).
    @discardableResult
    func untie(_ folderId: String) async -> Bool {
        errorMessage = nil
        do {
            switch try await client.api.untieFolderApiSyncFoldersFolderIdDelete(path: .init(folderId: folderId)) {
            case .ok:
                folders.removeAll { $0.id == folderId }
                intakeStates[folderId] = nil
                return true
            case .unprocessableContent:
                errorMessage = "The engine did not understand which folder to untie."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not untie this folder (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = "Could not untie this folder: \(error.localizedDescription)"
        }
        return false
    }

    // MARK: Helpers

    private func fetchFolders() async throws -> [Components.Schemas.SyncFolderStatus] {
        try await client.api.listFoldersApiSyncFoldersGet().ok.body.json.folders
    }

    /// One folder joins the list, or replaces its own entry, in place.
    private func splice(_ folder: Components.Schemas.SyncFolderStatus) {
        if let index = folders.firstIndex(where: { $0.id == folder.id }) {
            folders[index] = folder
        } else {
            folders.append(folder)
        }
    }

    static func canonical(_ path: String) -> String {
        URL(fileURLWithPath: path).standardizedFileURL.resolvingSymlinksInPath().path
    }

    /// A refusal in words (a 422 whose `detail` is a sentence) cannot decode as the generated
    /// validation shape: say the engine's sentence, never the decoding error.
    private static func engineWords(_ error: Error) async -> String? {
        guard let clientError = error as? ClientError, let body = clientError.responseBody,
              let data = try? await Data(collecting: body, upTo: 1 << 16) else { return nil }
        return EngineErrorDetail.message(from: data)
    }
}
