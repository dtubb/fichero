import Foundation

extension MobileCaptureQueueStore {
    var pendingCount: Int {
        items.filter {
            $0.uploadState == .queued || $0.uploadState == .failed || $0.uploadState == .waitingForBackend
        }.count
    }

    var uploadedCount: Int {
        items.filter { $0.uploadState == .uploaded }.count
    }

    func imageURL(for item: MobileCaptureQueueItem) -> URL {
        assetsDirectoryURL.appendingPathComponent(item.imageFileName)
    }
}
