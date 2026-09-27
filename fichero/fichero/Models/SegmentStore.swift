import FicheroAPIClient
import Foundation
import Observation

/// The single owner of a document's segments and passes (source-model App
/// slice A, #4954: `source.app.one-segment-store`). The ONLY caller of
/// `SegmentService` — nothing else in the app keeps segments. Keyed by
/// document id so loading (or later, patching) one document's entry never
/// touches another's.
///
/// Stage 2 as of 2026-09-27: `ChangeEventConsumer` conformance
/// (`source.app.segment-events-patch-in-place`). The stage-1 note said this had to
/// wait "after the engine's `segment_ids`/`pass_ids` change-stream fields exist —
/// wiring it against events that cannot fire yet would be untestable and
/// untested". That was true when written and is not now: `segment_ids` is emitted
/// by `reading_orders.py` (three sites), `typed_links.py` and
/// `segment_conversion.py`, and `pass_ids` by `segments.py` (three sites) and
/// `content_representations.py`.
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

    /// One store per `SegmentService`, the same keyed-singleton idiom
    /// `ArtifactEntityStore.shared(for:)` uses — and for the same reason: the
    /// drawing paths resolve the store from the service they already hold, so the
    /// instance `LibraryManager` registers with the change stream IS the instance a
    /// loader reads, with no new plumbing between them.
    ///
    /// `source.app.one-segment-store` is the whole point: a second instance would be
    /// a second store, so construction is funnelled through here rather than left to
    /// each caller.
    @MainActor private static var registry: [ObjectIdentifier: SegmentStore] = [:]

    static func shared(for service: SegmentService) -> SegmentStore {
        let key = ObjectIdentifier(service)
        if let existing = registry[key] { return existing }
        let store = SegmentStore(service: service)
        registry[key] = store
        return store
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

    // MARK: - Reacting to change events (`source.app.segment-events-patch-in-place`)

    /// What an event asks this store to do. A PURE decision, separated from doing
    /// it for the same reason `SegmentDisplay` splits its mapping half out: the
    /// interesting claim — "those items and no others" — is a claim about the
    /// decision, and a test can make it without a service, a task or a clock.
    enum ChangePlan: Equatable {
        /// Nothing here concerns a document this store holds.
        case nothing
        /// Re-read exactly these segment rows, leaving every other row alone.
        case patch(segmentIds: [String])
        /// This document's results changed and the event does not say which rows,
        /// so its list is re-read. ONE document, never the whole store.
        case reload(documentIds: [String])
    }

    /// The decision, given what the store holds.
    ///
    /// Rules, in order:
    ///
    /// * segments this store holds and the event names → **patch those**. This is
    ///   the case the behaviour is about, and the reason it is not a reload: a
    ///   reload re-reads rows nobody touched, which loses selection and scroll and
    ///   makes every event cost a page.
    /// * no named segment this store holds, but the event names a document it has
    ///   loaded → **reload that document**, because the row set itself may have
    ///   changed (a split adds rows; a delete removes one) and a patch of named
    ///   ids cannot express "there is one more row than before".
    /// * a document this store has never loaded → **nothing**. Loading on an event
    ///   would fetch pages nobody is looking at.
    nonisolated static func plan(
        for event: ChangeEvent,
        heldSegmentIds: Set<String>,
        loadedDocumentIds: Set<String>
    ) -> ChangePlan {
        let named = event.segmentIds.filter { heldSegmentIds.contains($0) }
        if !named.isEmpty {
            return .patch(segmentIds: named)
        }
        let documents = event.documentIds.filter { loadedDocumentIds.contains($0) }
        if !documents.isEmpty {
            return .reload(documentIds: documents)
        }
        return .nothing
    }

    /// Replace ONE segment in place, keeping its position in the document's array.
    ///
    /// Position is the engine's index (`source.app.index-is-the-engines`), so a
    /// patch must never reorder or append: a replacement that moved a row would
    /// change what every index-addressed reader means by that box. A segment the
    /// engine can no longer resolve is dropped, and a row this store does not hold
    /// is ignored rather than appended — an event about somebody else's page is
    /// not an instruction to load it.
    func patch(segmentId: String, with replacement: Segment?) {
        for (documentId, rows) in segmentsByDocument {
            guard let index = rows.firstIndex(where: { $0.id == segmentId }) else { continue }
            var updated = rows
            if let replacement {
                updated[index] = replacement
            } else {
                updated.remove(at: index)
            }
            segmentsByDocument[documentId] = updated
            return
        }
    }

    private var heldSegmentIds: Set<String> {
        Set(segmentsByDocument.values.flatMap { $0 }.map(\.id))
    }
}

extension SegmentStore: ChangeEventConsumer {
    /// `segment.*` and `pass.*`. Not `artifact.*`: an artifact event says a RESULT
    /// changed, and until a pass is the thing the app edits, reacting to it here
    /// would re-read a page on every workflow run that touched it.
    nonisolated var changeDomains: Set<String> { ["segment", "pass"] }

    func apply(_ event: ChangeEvent) {
        switch Self.plan(
            for: event,
            heldSegmentIds: heldSegmentIds,
            loadedDocumentIds: Set(segmentsByDocument.keys)
        ) {
        case .nothing:
            return
        case .patch(let segmentIds):
            for segmentId in segmentIds {
                Task { [weak self] in
                    guard let self else { return }
                    let replacement = try? await self.service.segment(id: segmentId)
                    self.patch(segmentId: segmentId, with: replacement)
                }
            }
        case .reload(let documentIds):
            for documentId in documentIds {
                Task { [weak self] in
                    await self?.load(documentId: documentId, force: true)
                }
            }
        }
    }

    /// After a reconnect, every loaded document is re-read: the stream has no
    /// replay, so events missed while it was down are unknowable and a patch
    /// cannot be aimed. This is the ONE place a wholesale re-read is right.
    func resync() async {
        for documentId in segmentsByDocument.keys {
            await load(documentId: documentId, force: true)
        }
    }
}
