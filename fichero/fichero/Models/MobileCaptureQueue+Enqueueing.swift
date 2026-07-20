import Foundation

extension MobileCaptureQueueStore {
    @discardableResult
    func enqueueCapturedImage(
        _ imageData: Data,
        catalog: MobileCaptureCatalogFields = .init(),
        fileName: String? = nil,
        fileExtension: String = "jpg"
    ) throws -> MobileCaptureQueueItem {
        try prepareStorage()

        let id = UUID().uuidString
        let resolvedFileName = fileName ?? "\(id).\(fileExtension)"
        let imageURL = assetsDirectoryURL.appendingPathComponent(resolvedFileName)
        try imageData.write(to: imageURL, options: .atomic)

        let now = Date()
        let item = MobileCaptureQueueItem(
            id: id,
            imageFileName: resolvedFileName,
            createdAt: now,
            updatedAt: now,
            catalog: catalog,
            uploadState: .queued,
            uploadedDocumentId: nil,
            lastError: nil,
            requiresExplicitRetry: false,
            retryCount: 0,
            lastAttemptAt: nil
        )
        items.insert(item, at: 0)
        persistQueue()
        return item
    }

    func updateCatalog(
        id: String,
        mutate: (inout MobileCaptureCatalogFields) -> Void
    ) {
        guard let index = items.firstIndex(where: { $0.id == id }) else { return }
        let wasInterruptedRetry =
            items[index].requiresExplicitRetry
            || items[index].lastError == Self.interruptedUploadError
        mutate(&items[index].catalog)
        items[index].updatedAt = Date()
        if items[index].uploadState == .uploaded {
            items[index].uploadState = .queued
            items[index].uploadedDocumentId = nil
            items[index].requiresExplicitRetry = false
        } else if wasInterruptedRetry {
            items[index].uploadState = .failed
            items[index].requiresExplicitRetry = true
            items[index].lastError = Self.interruptedUploadError
        } else if items[index].uploadState != .uploading {
            items[index].uploadState = .queued
        }
        if !wasInterruptedRetry {
            items[index].lastError = nil
        }
        persistQueue()
    }
}
