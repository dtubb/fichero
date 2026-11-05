import Foundation
import Observation

/// The cleanup-batch sheet's state (`image.enhance.batch-preview-undo`, #6192): one preview of three pages, one apply, one undo.
@MainActor @Observable
final class ImageCleanupBatchModel {
    enum Phase: Equatable { case loading, ready, applied(batchId: String), undone, failed(String) }

    let folderId: String
    let step: CleanupStep
    private let folderPages: [CleanupPageRef]
    private let service: any ImageCleanupBatching

    private(set) var phase: Phase = .loading
    private(set) var preview = CleanupPreview(pages: 0, samples: [])
    /// The pages the batch changed, each with its own Undo once it is applied.
    private(set) var appliedPages: [CleanupPageRef] = []

    init(folderId: String, step: CleanupStep, pages: [CleanupPageRef], service: any ImageCleanupBatching) {
        self.folderId = folderId
        self.folderPages = pages
        self.step = step
        self.service = service
    }

    var summary: String {
        "\(step.title) on \(preview.pages) page\(preview.pages == 1 ? "" : "s") in this folder."
    }

    func loadPreview() async {
        do {
            preview = try await service.preview(folderId: folderId, step: step)
            phase = .ready
        } catch {
            phase = .failed("Couldn't preview: \(error.localizedDescription)")
        }
    }

    func apply() async {
        guard phase == .ready else { return }
        do {
            phase = .applied(batchId: try await service.apply(folderId: folderId, step: step))
            appliedPages = folderPages
        } catch {
            phase = .failed("Couldn't apply: \(error.localizedDescription)")
        }
    }

    /// Undo all: the batch's rows leave every page, nothing else.
    func undoAll() async {
        guard case .applied(let batchId) = phase else { return }
        do {
            try await service.undo(batchId: batchId)
            appliedPages = []
            phase = .undone
        } catch {
            phase = .failed("Couldn't undo: \(error.localizedDescription)")
        }
    }

    func pageUndone(_ id: String) { appliedPages.removeAll { $0.id == id } }
}
