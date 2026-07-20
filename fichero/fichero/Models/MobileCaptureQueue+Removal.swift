import Foundation

extension MobileCaptureQueueStore {
    func removeItem(id: String) {
        guard let index = items.firstIndex(where: { $0.id == id }) else { return }
        let item = items.remove(at: index)
        try? fileManager.removeItem(at: imageURL(for: item))
        persistQueue()
    }
}
