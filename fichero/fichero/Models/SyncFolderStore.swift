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
    /// Keep arranged, proposed and not yet said yes to: each folder's dry run
    /// (`GET /api/sync-folders/{id}/arrangement`), shown with Arrange until the person answers
    /// (`source.onboard.keep-arranged`). Nothing moves while a folder is in here.
    private(set) var proposedArrangements: [String: Components.Schemas.ArrangementPreview] = [:]
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
                proposedArrangements[folderId] = nil
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

    // MARK: Keep arranged (#5480, source.onboard.keep-arranged)

    /// Propose keeping a folder arranged: read the dry run (what would move, from and to, or why
    /// it would be refused) and hold it for the person to see. Nothing moves: the mode is not
    /// changed here, because the engine arranges a folder as soon as it is kept arranged (a tie
    /// with `keep-arranged` or `PUT …/mode` queues the first arrangement). Returns the preview.
    @discardableResult
    func proposeKeepArranged(_ folderId: String) async -> Components.Schemas.ArrangementPreview? {
        errorMessage = nil
        do {
            switch try await client.api.getArrangementApiSyncFoldersFolderIdArrangementGet(
                path: .init(folderId: folderId)
            ) {
            case .ok(let success):
                let preview = try success.body.json
                proposedArrangements[folderId] = preview
                return preview
            case .unprocessableContent:
                errorMessage = "The engine did not understand which folder to arrange."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not work out what keeping this folder arranged would move (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return nil }
            errorMessage = await Self.engineWords(error)
                ?? "Could not work out what keeping this folder arranged would move: \(error.localizedDescription)"
        }
        return nil
    }

    /// The mode a folder's Inspector shows: Keep arranged while it is proposed (its dry run on
    /// screen, nothing moved yet), else the engine's.
    func shownMode(of folder: Components.Schemas.SyncFolderStatus) -> Components.Schemas.SyncFolderStatus.ModePayload {
        proposedArrangements[folder.id] != nil ? .keepArranged : folder.mode
    }

    /// The Inspector's Index / Keep arranged choice (`source.onboard.keep-arranged`). Choosing
    /// Keep arranged reads the dry run and changes nothing (the yes is `confirmKeepArranged`);
    /// choosing Index drops a proposal, or keeps an arranged folder as Index (nothing moves).
    @discardableResult
    func choose(_ mode: Components.Schemas.SyncFolderStatus.ModePayload, for folderId: String) async -> Bool {
        guard let folder = folders.first(where: { $0.id == folderId }) else { return false }
        switch mode {
        case .keepArranged:
            guard folder.mode != .keepArranged else { return true }
            return await proposeKeepArranged(folderId) != nil
        case .index:
            if proposedArrangements[folderId] != nil {
                cancelKeepArranged(folderId)
                return true
            }
            guard folder.mode != .index else { return true }
            return await setMode(folderId, to: .index)
        }
    }

    /// The person said no to the proposal: it goes, and nothing moved.
    func cancelKeepArranged(_ folderId: String) {
        proposedArrangements[folderId] = nil
    }

    /// The yes: keep the folder arranged (`PUT /api/sync-folders/{id}/mode`), which arranges it
    /// now (one audited, undoable action listing every move) and from then on.
    @discardableResult
    func confirmKeepArranged(_ folderId: String) async -> Bool {
        let kept = await setMode(folderId, to: .keepArranged)
        if kept { proposedArrangements[folderId] = nil }
        return kept
    }

    /// Keep a folder as Index or Keep arranged (`PUT /api/sync-folders/{id}/mode`); the folder's
    /// entry is replaced in place by the status the engine returns. Switching to Keep arranged
    /// goes through `proposeKeepArranged` first; this is its yes. A refusal (a folder that cannot
    /// be written to) is the engine's sentence.
    @discardableResult
    func setMode(_ folderId: String, to mode: Components.Schemas.ModeRequest.ModePayload) async -> Bool {
        errorMessage = nil
        do {
            switch try await client.api.putModeApiSyncFoldersFolderIdModePut(
                path: .init(folderId: folderId), body: .json(.init(mode: mode))
            ) {
            case .ok(let success):
                splice(try success.body.json)
                return true
            case .unprocessableContent:
                errorMessage = "The engine would not change how this folder is kept."
            case .undocumented(let code, let body):
                errorMessage = await EngineErrorDetail.message(from: body)
                    ?? "Could not change how this folder is kept (HTTP \(code))"
            }
        } catch {
            if error.isCancellationError { return false }
            errorMessage = await Self.engineWords(error)
                ?? "Could not change how this folder is kept: \(error.localizedDescription)"
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
