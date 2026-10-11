import Foundation

// MARK: - Add material (Set Up's Add material, section 7d)

/// Adding material into the project being set up, split from `RecipeSetupStore` (its file is at its length limit).
extension RecipeSetupStore {
    /// Import a folder into the project the way setup chose (link, copy, move
    /// or index), through the project's own import path. Importing is not
    /// Start: no recipe step runs on it. With Index, the folder is then tied
    /// through `/api/sync-folders` (`source.onboard.index-ties-the-folder`), so
    /// Index is whole and not only a recorded mode; `tiedFolderPath` names it
    /// for the screen to show. With Keep arranged the folder is tied the same way (as Index, so
    /// nothing moves yet) and its dry run is read and shown with Arrange: the engine arranges a
    /// folder the moment it is kept arranged, so the mode changes only on that yes
    /// (`source.onboard.keep-arranged`, `SyncFolderStore.confirmKeepArranged`).
    func addFolder(_ url: URL, importer: ImportService, syncFolders: SyncFolderStore? = nil) async {
        materialAdded = nil
        tiedFolderPath = nil
        do {
            let ids = try await importer.importFolder(url, mode: ingestMode)
            materialAdded = "\(url.lastPathComponent): \(ids.count) added (\(wayIn.title.lowercased()))."
            if ingestMode == .index, let syncFolders {
                if let tied = await syncFolders.tie(path: url.path) {
                    tiedFolderPath = url.path
                    if keepsArranged, tied.mode != .keepArranged,
                       await syncFolders.proposeKeepArranged(tied.id) == nil {
                        errorMessage = syncFolders.errorMessage
                    }
                } else {
                    errorMessage = syncFolders.errorMessage
                }
            }
        } catch {
            if error.isCancellationError { return }
            errorMessage = "Could not add \(url.lastPathComponent): \(error.localizedDescription)"
        }
    }

    /// Add files, or several folders at once (section 7d, Add Files or Folders…): through the project's import path,
    /// the way setup chose. One folder alone goes through `addFolder`, which also ties an Index folder.
    ///
    /// Into THIS project (the importer is the project's own, on its client and library path), never the always-there
    /// one: each folder through `POST /api/ingest/folder` (granted first), the loose files through the files import;
    /// a folder is never recorded as a file (2026-10-11: Set Up's material never reached the project, and a folder
    /// became one "file"). Start waits while it is adding (`isAddingMaterial`); the pages are counted after.
    func addMaterial(_ urls: [URL], importer: ImportService, syncFolders: SyncFolderStore? = nil) async {
        guard !urls.isEmpty else { return }
        isAddingMaterial = true
        defer { isAddingMaterial = false }
        let folders = urls.filter(ImportService.isDirectory)
        let files = urls.filter { !folders.contains($0) }
        var said: [String] = []
        for folder in folders {
            await addFolder(folder, importer: importer, syncFolders: syncFolders)
            if let added = materialAdded { said.append(added) }
        }
        if !files.isEmpty {
            do {
                let outcome = try await importer.importFiles(files, mode: ingestMode)
                let failed = outcome.failures.isEmpty ? "" : ", \(outcome.failures.count) could not be added"
                said.append("\(files.count) file\(files.count == 1 ? "" : "s") added (\(wayIn.title.lowercased()))\(failed).")
            } catch {
                if !error.isCancellationError { errorMessage = "Could not add the files: \(error.localizedDescription)" }
            }
        }
        materialAdded = said.isEmpty ? nil : said.joined(separator: " ")
    }
}
