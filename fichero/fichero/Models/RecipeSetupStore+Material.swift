import Foundation

// MARK: - Add material (Set Up's Add material, section 7d)

/// Adding material into the project being set up, split from `RecipeSetupStore` (its file is at its length limit).
extension RecipeSetupStore {
    /// The project has material: something was added in this Set Up, or the engine counts pages already there
    /// (Your Material's Continue waits for it, #5813).
    var hasMaterial: Bool { materialAdded != nil || (countedPages ?? 0) > 0 }

    /// What a "no material yet" refusal says while this Set Up has already added something: the engine counts no page
    /// until the import lands, so the person is told the pages are on their way, not that there are none (review 208).
    static let pagesStillComingIn = "Your pages are still coming in; the plan follows when they have landed."

    /// The engine's refusal sentence, or `pagesStillComingIn` when it is the no-material one and material was added.
    func refusalWords(_ detail: String?, fallback: String) -> String {
        guard let detail else { return fallback }
        return materialAdded != nil && detail.contains("has no material yet") ? Self.pagesStillComingIn : detail
    }

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
        // Before the copy starts, off the main actor: a big folder is walked without stalling the window.
        copySpace = nil
        if ingestMode == .copy {
            let bytes = await Self.byteSize(of: urls)
            copySpace = Self.copySpaceSentence(bytes: bytes, free: RecipeDownloadRows.freeDiskBytes())
        }
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

    /// The bytes a Copy takes: every regular file under the chosen files and folders (what the copy duplicates).
    @concurrent static func byteSize(of urls: [URL]) async -> Int64 {
        let keys: Set<URLResourceKey> = [.isRegularFileKey, .fileSizeKey]
        var total: Int64 = 0
        for url in urls {
            let values = try? url.resourceValues(forKeys: keys)
            if values?.isRegularFile == true { total += Int64(values?.fileSize ?? 0); continue }
            guard let walk = FileManager.default.enumerator(at: url, includingPropertiesForKeys: Array(keys)) else { continue }
            for case let file as URL in walk.allObjects {
                let inner = try? file.resourceValues(forKeys: keys)
                if inner?.isRegularFile == true { total += Int64(inner?.fileSize ?? 0) }
            }
        }
        return total
    }

    /// "The copy takes 1.2 GB; 112 GB free." (the free room when known), said before Start.
    nonisolated static func copySpaceSentence(bytes: Int64, free: Int64?) -> String {
        let size = ByteCountFormatter.string(fromByteCount: bytes, countStyle: .file)
        guard let free else { return "The copy takes \(size)." }
        return "The copy takes \(size); \(ByteCountFormatter.string(fromByteCount: free, countStyle: .file)) free."
    }
}
