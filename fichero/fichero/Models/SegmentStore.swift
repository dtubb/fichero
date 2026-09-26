import FicheroAPIClient
import Foundation
import Observation

/// The single owner of a document's segments and passes (source-model App
/// slice A, #4954: `source.app.one-segment-store`). The ONLY caller of
/// `SegmentService` — nothing else in the app keeps segments. Keyed by
/// document id so loading (or later, patching) one document's entry never
/// touches another's.
///
/// Stage 1 only: load, hold, read. `ChangeEventConsumer` conformance
/// (`source.app.segment-events-patch-in-place`) is stage 2, after the engine's
/// `segment_ids`/`pass_ids` change-stream fields exist — wiring it against
/// events that cannot fire yet would be untestable and untested.
@MainActor
@Observable
final class SegmentStore {
    private(set) var segmentsByDocument: [String: [Segment]] = [:]
    private(set) var passesByDocument: [String: [SegmentPassValue]] = [:]
    private(set) var loadingDocumentIds: Set<String> = []
    private(set) var loadErrorsByDocumentId: [String: String] = [:]

    private let service: SegmentService

    init(service: SegmentService) {
        self.service = service
    }

    /// Load one document's segments and passes. Idempotent against an
    /// already-loaded document unless `force` — the same shape
    /// `EntityStore.loadEntities(forDocument:)` uses. Replaces ONLY this
    /// document's entry in both dictionaries; every other loaded document's
    /// arrays are untouched (no wholesale reload).
    func load(documentId: String, force: Bool = false) async {
        if !force, segmentsByDocument[documentId] != nil, loadErrorsByDocumentId[documentId] == nil {
            return
        }
        loadingDocumentIds.insert(documentId)
        loadErrorsByDocumentId[documentId] = nil
        defer { loadingDocumentIds.remove(documentId) }
        do {
            let result = try await service.listDocumentSegments(documentId: documentId)
            passesByDocument[documentId] = result.passes
            segmentsByDocument[documentId] = result.segments
        } catch {
            if error.isCancellationError { return }
            loadErrorsByDocumentId[documentId] = error.localizedDescription
        }
    }

    func segments(documentId: String) -> [Segment] {
        segmentsByDocument[documentId] ?? []
    }

    func passes(documentId: String) -> [SegmentPassValue] {
        passesByDocument[documentId] ?? []
    }

    func isLoading(documentId: String) -> Bool {
        loadingDocumentIds.contains(documentId)
    }

    func loadError(documentId: String) -> String? {
        loadErrorsByDocumentId[documentId]
    }
}
