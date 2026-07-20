import Foundation

extension MobileCaptureQueueStore {
    func markAllWaitingForBackend() {
        var changed = false
        for index in items.indices where items[index].uploadState == .queued || items[index].uploadState == .failed {
            items[index].uploadState = .waitingForBackend
            if items[index].lastError != Self.interruptedUploadError {
                items[index].lastError = nil
            }
            changed = true
        }
        if changed { persistQueue() }
    }

    @discardableResult
    func resumePendingUploads(
        using uploader: some MobileCaptureQueueUploading,
        retryInterruptedUploads: Bool = false
    ) async -> MobileCaptureUploadSummary {
        guard MobileCaptureQueueRouting.canResumeUploads(backendHost: uploader.backendHost) else {
            markAllWaitingForBackend()
            return MobileCaptureUploadSummary(waitingCount: pendingCount)
        }

        var summary = MobileCaptureUploadSummary()
        let retryableIndices = items.indices.filter { index in
            switch items[index].uploadState {
            case .queued, .failed, .waitingForBackend:
                if items[index].requiresExplicitRetry && !retryInterruptedUploads {
                    return false
                }
                if !retryInterruptedUploads,
                   items[index].lastError == Self.interruptedUploadError {
                    return false
                }
                return true
            case .uploading, .uploaded:
                return false
            }
        }

        for index in retryableIndices {
            items[index].uploadState = .uploading
            items[index].lastAttemptAt = Date()
            items[index].retryCount += 1
            items[index].lastError = nil
        }
        persistQueue()

        for index in retryableIndices {
            let item = items[index]
            do {
                let documentId = try await uploader.upload(
                    fileURL: imageURL(for: item),
                    catalog: item.catalog
                )
                items[index].uploadState = .uploaded
                items[index].uploadedDocumentId = documentId
                items[index].lastError = nil
                summary.uploadedCount += 1
            } catch {
                items[index].uploadState = .failed
                items[index].lastError = error.localizedDescription
                summary.failedCount += 1
                Self.logger.error("Capture upload failed: \(error.localizedDescription)")
            }
            persistQueue()
        }

        return summary
    }
}
