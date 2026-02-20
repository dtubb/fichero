import SwiftUI

extension BatchDetailView {
    func refreshBatch() async {
        guard let library = libraryManager.openLibraries.first else { return }

        isLoading = true
        defer { isLoading = false }

        do {
            refreshedBatch = try await library.batchService.getBatchAsInfo(
                batchId: batch.batchId,
                includeItems: true
            )
        } catch {
            batchDetailLogger.error("Failed to refresh batch: \(error.localizedDescription)")
            self.error = error.localizedDescription
        }
    }

    func pauseBatch() async {
        guard let library = libraryManager.openLibraries.first else { return }

        do {
            refreshedBatch = try await library.batchService.pauseBatchAsInfo(batchId: batch.batchId)
        } catch {
            batchDetailLogger.error("Failed to pause batch: \(error.localizedDescription)")
        }
    }

    func resumeBatch() async {
        guard let library = libraryManager.openLibraries.first else { return }

        do {
            try await library.batchService.resumeBatch(batchId: batch.batchId)
            await refreshBatch()
        } catch {
            batchDetailLogger.error("Failed to resume batch: \(error.localizedDescription)")
        }
    }

    func cancelBatch() async {
        guard let library = libraryManager.openLibraries.first else { return }

        do {
            refreshedBatch = try await library.batchService.cancelBatchAsInfo(batchId: batch.batchId)
        } catch {
            batchDetailLogger.error("Failed to cancel batch: \(error.localizedDescription)")
        }
    }

    func retryBatch() async {
        guard let library = libraryManager.openLibraries.first else { return }

        do {
            try await library.batchService.retryBatch(batchId: batch.batchId)
            await refreshBatch()
        } catch {
            batchDetailLogger.error("Failed to retry batch: \(error.localizedDescription)")
        }
    }
}
