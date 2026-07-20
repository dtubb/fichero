import Foundation

extension MobileCaptureQueueStore {
    // Internal to allow access from init and other extensions
    func loadPersistedQueue() {
        guard fileManager.fileExists(atPath: manifestURL.path),
              let data = try? Data(contentsOf: manifestURL),
              let decoded = try? JSONDecoder().decode([MobileCaptureQueueItem].self, from: data)
        else {
            items = []
            return
        }

        items = decoded.compactMap { item in
            guard fileManager.fileExists(atPath: imageURL(for: item).path) else {
                return nil
            }

            var normalized = item
            if normalized.uploadState == .uploading {
                normalized.uploadState = .failed
                normalized.lastError = Self.interruptedUploadError
                normalized.requiresExplicitRetry = true
                normalized.lastAttemptAt = nil
            }
            return normalized
        }
    }

    func persistQueue() {
        do {
            try prepareStorage()
            let data = try JSONEncoder().encode(items)
            try data.write(to: manifestURL, options: .atomic)
        } catch {
            Self.logger.error("Failed to persist capture queue: \(error.localizedDescription)")
        }
    }

    func prepareStorage() throws {
        if !fileManager.fileExists(atPath: storageDirectory.path) {
            try fileManager.createDirectory(at: storageDirectory, withIntermediateDirectories: true)
        }
        if !fileManager.fileExists(atPath: assetsDirectoryURL.path) {
            try fileManager.createDirectory(at: assetsDirectoryURL, withIntermediateDirectories: true)
        }
    }

    static func defaultStorageDirectory(fileManager: FileManager) -> URL {
        let baseURL = fileManager.urls(for: .applicationSupportDirectory, in: .userDomainMask).first
            ?? fileManager.temporaryDirectory
        return baseURL.appendingPathComponent("Fichero/MobileCaptureQueue", isDirectory: true)
    }
}
