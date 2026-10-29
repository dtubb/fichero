#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import Foundation
import Observation
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageEditorModel")

/// View-model for the non-destructive image editor (#469).
///
/// Owns the `ImageEditingService` and all async state so the view
/// stays declarative. Every mutating op follows the same shape: run the
/// backend op, refresh the chain, then re-render the *edited* preview so the
/// canvas reflects the new chain immediately.
@MainActor
@Observable
final class ImageEditorModel {
    typealias PreviewLoader = @MainActor (_ documentId: String, _ applyEdits: Bool, _ page: Int) async throws -> PreviewImage

    /// Currently displayed preview (original or edited, per `showEdited`).
    var preview: PreviewImage?
    /// Cached original preview (apply_edits=false) for A/B compare UI.
    var originalPreview: PreviewImage?
    /// Cached edited preview (apply_edits=true) for A/B compare UI.
    var editedPreview: PreviewImage?
    /// The document's saved edit chain.
    var chain: ImageEditChain
    /// #469 toggle — false shows the untouched source, true shows the chain applied.
    var showEdited: Bool = true
    /// 1-indexed page (PDF documents); always 1 for single images.
    var page: Int = 1
    /// True while any op / load is in flight (drives the busy overlay + disables controls).
    var isBusy: Bool = false
    var errorMessage: String?
    /// Bidirectional selection between inspector and canvas (#1420).
    /// The inspector highlights this step; the canvas could show an overlay handle.
    var selectedStepIndex: Int?

    /// The `StorageService` image epoch this model has already accounted for.
    ///
    /// Two `ImageEditorModel`s are alive whenever the editor is open — the
    /// Preview canvas owns one, the Inspector's Edits facet owns the other —
    /// and neither could see the other's work: applying a rotate from the
    /// canvas toolbar left the Inspector's step list empty, and applying an
    /// Enhance from the Inspector left the canvas showing the pre-edit pixels
    /// (Daniel, 2026-09-03: "image steps not really showing the steps").
    /// Every successful op already bumps `StorageService.imageEpoch` for the
    /// document, so that counter is the one signal both models can watch —
    /// the same fix shape as `LibraryImageView`'s load key.
    private(set) var seenEpoch: Int = 0

    /// Called after every successful edit or reset so the caller can evict
    /// stale storage-display caches for the affected document. Set from
    /// `ImageEditorView` once the view is configured.
    var onEditApplied: ((String) -> Void)?

    private var service: ImageEditingService?
    private(set) var documentId: String = ""

    /// Client-side Core Image live-preview compositor (#3673). Built lazily from
    /// `originalPreview`, cached, and evicted on document change / chain reset.
    /// PROVISIONAL only — the server render replaces its frame on commit; the
    /// `ImageEditChain` stays the sole source of truth. Never observed directly.
    @ObservationIgnored private var liveEditPreview: LiveEditPreview?

    /// In-flight original↔edited toggle. Tracked so rapid taps coalesce to the
    /// latest intended state instead of running out of order (#1508).
    private var toggleTask: Task<Void, Never>?
    private let previewLoader: PreviewLoader?

    init(documentId: String = "", previewLoader: PreviewLoader? = nil) {
        self.documentId = documentId
        self.chain = ImageEditChain(documentId: documentId, operations: [], updatedAt: nil)
        self.previewLoader = previewLoader
    }

    /// Bind to a document. Safe to call repeatedly (e.g. on prev/next nav) —
    /// rebuilds state for the new document and reloads chain + preview.
    ///
    /// `loadsPreviews: false` is for a host that renders the CHAIN and no
    /// pixels — the Inspector's Edits facet. It showed a step list and then
    /// downloaded two full renders of the image nobody was looking at, on
    /// every open and every external edit.
    func configure(
        apiClient: APIClient,
        documentId: String,
        page: Int = 1,
        epoch: Int = 0,
        loadsPreviews: Bool = true
    ) async {
        if service == nil {
            service = ImageEditingService(apiClient: apiClient)
        }
        self.documentId = documentId
        self.page = page
        self.seenEpoch = epoch
        self.loadsPreviews = loadsPreviews
        self.chain = ImageEditChain(documentId: documentId, operations: [], updatedAt: nil)
        self.preview = nil
        self.originalPreview = nil
        self.editedPreview = nil
        // Drop the client live-preview cache — the original bytes belong to the
        // previous document (#3673). It rebuilds lazily on the next slider drag.
        self.liveEditPreview = nil
        await reload()
    }

    // MARK: - Client-side live preview (#3673)

    /// Composite an in-progress enhance/rotate LOCALLY (no backend) for a
    /// continuously-dragged slider, so it previews at ~60fps. Sets `preview` to a
    /// provisional Core Image frame over the ORIGINAL bytes; the next commit
    /// (`enhance`/`rotate`) resyncs it from the server. A no-op until the original
    /// has loaded. This never touches the chain and adds no network call.
    func previewLiveEdit(
        brightness: Double = 1,
        contrast: Double = 1,
        sharpen: Double = 1,
        angleDegrees: Double = 0
    ) {
        if liveEditPreview == nil, let original = originalPreview?.image {
            liveEditPreview = LiveEditPreview(original: original)
        }
        guard let liveEditPreview,
              let frame = liveEditPreview.render(
                  brightness: brightness,
                  contrast: contrast,
                  sharpen: sharpen,
                  angleDegrees: angleDegrees
              )
        else { return }
        preview = frame
    }

    /// Discard the provisional live frame and restore the authoritative preview —
    /// e.g. when the user dismisses a slider without committing (#3673).
    func discardLiveEdit() {
        preview = showEdited ? editedPreview : originalPreview
    }

    /// Adopt an edit somebody ELSE committed to this document.
    ///
    /// Called by the host on every `StorageService` epoch change. A change the
    /// model made itself was already accounted for in `runOp`/`resetAll`, so
    /// this no-ops on it and costs nothing — only a genuinely external edit
    /// (the other panel, a workflow, a batch apply) re-fetches.
    func syncIfExternallyEdited(epoch: Int) async {
        guard epoch != seenEpoch, !documentId.isEmpty else { return }
        seenEpoch = epoch
        await loadChain()
        await reloadPreviews(forceOriginalReload: false, forceEditedReload: true)
    }

    /// Reload both the chain and the current preview.
    func reload() async {
        await loadChain()
        await reloadPreviews(forceOriginalReload: true, forceEditedReload: true)
    }

    /// False for a chain-only host (see `configure(loadsPreviews:)`).
    private var loadsPreviews = true

    private func loadChain() async {
        guard let service, !documentId.isEmpty else { return }
        do {
            chain = try await service.getChain(documentId: documentId)
        } catch {
            // Superseded load (isCancellationError idiom): keep whatever chain
            // we have — replacing it with an empty one would erase real state
            // because the user merely navigated away mid-fetch.
            if error.isCancellationError { return }
            logger.error("getChain failed: \(error.localizedDescription)")
            // A missing chain is not an error worth surfacing — treat as empty.
            chain = ImageEditChain(documentId: documentId, operations: [], updatedAt: nil)
        }
    }

    /// Re-fetch the preview honouring the current `showEdited` toggle + page.
    ///
    /// `forceOriginalReload` stays false for normal edit/reset refreshes: the
    /// original source bytes do not change when the edit chain changes, so
    /// re-downloading them on every op just burns latency.
    func reloadPreviews(
        forceOriginalReload: Bool = false,
        forceEditedReload: Bool = true
    ) async {
        guard !documentId.isEmpty, loadsPreviews else { return }
        let shouldLoadOriginal = forceOriginalReload || originalPreview == nil
        let shouldLoadEdited = forceEditedReload || editedPreview == nil
        guard shouldLoadOriginal || shouldLoadEdited else {
            preview = showEdited ? editedPreview : originalPreview
            return
        }
        do {
            if shouldLoadOriginal && shouldLoadEdited {
                async let original = loadPreview(applyEdits: false)
                async let edited = loadPreview(applyEdits: true)
                originalPreview = try await original
                editedPreview = try await edited
            } else if shouldLoadOriginal {
                originalPreview = try await loadPreview(applyEdits: false)
            } else if shouldLoadEdited {
                editedPreview = try await loadPreview(applyEdits: true)
            }
            preview = showEdited ? editedPreview : originalPreview
        } catch {
            // A cancelled load is a SUPERSEDED load (the selection or page moved
            // on), not a failure — the codebase-wide isCancellationError idiom.
            // Logging it as an error spammed the iOS launch console
            // (Daniel, 2026-08-29), and surfacing it as `errorMessage` showed a
            // scary banner for a load nobody wanted anymore.
            if error.isCancellationError { return }
            logger.error("loadPreview failed: \(error.localizedDescription)")
            errorMessage = error.localizedDescription
        }
    }

    private func loadPreview(applyEdits: Bool) async throws -> PreviewImage {
        if let previewLoader {
            return try await previewLoader(documentId, applyEdits, page)
        }
        guard let service else { throw ImageEditingError.invalidResponse }
        return try await service.loadPreview(
            documentId: documentId,
            applyEdits: applyEdits,
            page: page
        )
    }

    /// Flip the original↔edited toggle and re-render (#469).
    func toggleEdited() {
        setShowEdited(!showEdited)
    }

    /// Set the original↔edited toggle to an explicit `target` and re-render.
    ///
    /// The target is captured synchronously by the caller (the view's Binding
    /// already knows the new value), not derived from `toggle()` at task-run
    /// time, and any in-flight toggle is cancelled — so two rapid taps always
    /// converge on the latest intended state rather than racing (#1508).
    ///
    /// The mutation is still deferred into a `Task` to avoid "Publishing changes
    /// from within view updates is not allowed" warnings, since this is called
    /// from a Binding `set:` closure (#1444).
    func setShowEdited(_ target: Bool) {
        toggleTask?.cancel()
        toggleTask = Task { @MainActor in
            self.showEdited = target
            self.preview = target ? self.editedPreview : self.originalPreview
            if self.preview == nil, !Task.isCancelled {
                await self.reloadPreviews(
                    forceOriginalReload: !target,
                    forceEditedReload: target
                )
            }
        }
    }

    // MARK: - Operations

    func rotate(by degrees: Double) async {
        await runOp { service in
            try await service.rotate(documentId: self.documentId, angle: degrees, page: self.page)
        }
    }

    func straighten() async {
        await runOp { service in
            try await service.straighten(documentId: self.documentId, page: self.page)
        }
    }

    func enhance(brightness: Double, contrast: Double, sharpen: Double, autoLevels: Bool) async {
        await runOp { service in
            try await service.enhance(
                documentId: self.documentId,
                brightness: brightness,
                contrast: contrast,
                sharpen: sharpen,
                autoLevels: autoLevels,
                page: self.page
            )
        }
    }

    func removeBackground(method: String = "opencv") async {
        await runOp { service in
            try await service.removeBackground(documentId: self.documentId, method: method, page: self.page)
        }
    }

    func segment(method: String = "foreground") async {
        await runOp { service in
            try await service.segment(documentId: self.documentId, method: method, page: self.page)
        }
    }

    /// Append a fuzzy_clean (despeckle) step via setOperations (#1420).
    func fuzzyClean(despeckleRadius: Int = 3) async {
        await runOp { service in
            var ops = self.chain.operations.map(\.raw)
            let newOp = AnyCodable([
                "op": "fuzzy_clean",
                "page": self.page,
                "params": ["despeckle_radius": despeckleRadius]
            ] as [String: Any])
            ops.append(newOp)
            return try await service.setOperations(documentId: self.documentId, operations: ops)
        }
    }

    /// Crop using a bbox already mapped to source pixels.
    func crop(left: Int, top: Int, width: Int, height: Int) async {
        await runOp { service in
            try await service.crop(
                documentId: self.documentId,
                left: left, top: top, width: width, height: height, page: self.page
            )
        }
    }

    /// Re-edit ONE committed step in place, keeping its position in the chain
    /// (Daniel, 2026-09-02: Aperture/Lightroom step editing — "click a step to
    /// re-open its settings, change them, and the stack reapplies from that
    /// point").
    ///
    /// The chain is the recipe, so changing a step is a chain rewrite, not a
    /// new operation: the passed `params` are merged onto the step at `index`
    /// and the whole list goes back through `PUT /edits`, after which the
    /// engine re-renders the document from the SOURCE through every step in
    /// order — which is exactly "reapplies from that point".
    ///
    /// Remove-then-re-add, which the panel used to do, is not the same thing:
    /// the new step lands at the END, so re-editing a rotate that sat before a
    /// crop silently moved it after the crop and changed the picture. It also
    /// spent two round-trips and two renders on one edit.
    func updateOperation(at index: Int, params: [String: Any]) async {
        guard chain.operations.indices.contains(index) else { return }
        await runOp { service in
            var ops = self.chain.operations.map(\.raw)
            guard var dict = ops[index].value as? [String: Any] else {
                throw ImageEditingError.invalidResponse
            }
            var merged = (dict["params"] as? [String: Any]) ?? [:]
            for (key, value) in params { merged[key] = value }
            dict["params"] = merged
            // `derived_path` names the cached render of the step's OLD
            // settings. Left in place it is a stale pointer the engine could
            // prefer over the recipe we just changed.
            dict.removeValue(forKey: "derived_path")
            ops[index] = AnyCodable(dict)
            return try await service.setOperations(documentId: self.documentId, operations: ops)
        }
    }

    // MARK: - Copy / Paste edits (Daniel, 2026-09-02)

    /// Put this document's chain on the app-wide edit clipboard.
    func copyEdits() {
        ImageEditClipboard.shared.copy(
            operations: chain.operations.map(\.raw),
            fromDocumentId: documentId
        )
    }

    /// Adopt the copied chain on the CURRENT document.
    ///
    /// Paste REPLACES rather than appends, the way Lightroom's Paste Settings
    /// does: pasting the same copy onto an image twice must leave it looking
    /// the way the source looks, not rotated twice.
    func pasteEdits() async {
        let operations = ImageEditClipboard.shared.operations
        guard !documentId.isEmpty else { return }
        await runOp { service in
            try await service.setOperations(
                documentId: self.documentId,
                operations: ImageEditClipboard.sanitized(operations)
            )
        }
    }

    /// Adopt the copied chain on many documents at once — the multi-selection
    /// form of Paste Edits. Failures are collected per document, like every
    /// other batch op, rather than aborting the rest.
    func pasteEdits(to documentIds: [String]) async {
        let operations = ImageEditClipboard.sanitized(ImageEditClipboard.shared.operations)
        await batchApply(documentIds: documentIds) { service, id in
            try await service.setOperations(documentId: id, operations: operations)
        }
    }

    func removeOperation(at index: Int) async {
        await runOp { service in try await service.removeOperation(documentId: self.documentId, at: index) }
    }

    /// Undo = drop the LAST committed step (Daniel, 2026-08-31). Steps commit
    /// on Apply, so undo is a chain rewrite (PUT minus the tail), not local state.
    func undoLastStep() async {
        guard !chain.isEmpty else { return }
        if selectedStepIndex == chain.operations.count - 1 { selectedStepIndex = nil }
        await removeOperation(at: chain.operations.count - 1)
    }

    /// Apply the same op across many documents (#1265 batch-apply).
    ///
    /// There is no backend batch endpoint, so this fans out client-side over
    /// the per-document op endpoints. Failures on individual documents are
    /// collected rather than aborting the whole batch; the active document's
    /// chain + preview are refreshed at the end.
    func batchApply(
        documentIds: [String],
        operation: @escaping (ImageEditingService, String) async throws -> Void
    ) async {
        guard let service, !documentIds.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        var failures = 0
        for id in documentIds {
            do {
                try await operation(service, id)
                // The active document's own bump is accounted for, so the
                // host's epoch observer stays quiet for it; siblings still
                // get their caches evicted so their rows repaint.
                if id == documentId { noteLocalEdit() } else { onEditApplied?(id) }
            } catch {
                failures += 1
                logger.error("batch op failed for \(id): \(error.localizedDescription)")
            }
        }
        if failures > 0 {
            errorMessage = "Batch applied with \(failures) failure(s) out of \(documentIds.count)."
        }
        await reload()
    }

    func resetAll() async {
        guard let service, !documentId.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            try await service.resetChain(documentId: documentId)
            chain = ImageEditChain(documentId: documentId, operations: [], updatedAt: nil)
            noteLocalEdit()
            await reloadPreviews(forceOriginalReload: false, forceEditedReload: true)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Record an edit this model just committed: evict the host's caches and
    /// move `seenEpoch` past the bump `invalidateImageCache` makes, so the
    /// host's epoch observer does not re-fetch what we already have.
    ///
    /// `invalidateImageCache` increments by exactly one per call and each
    /// successful op calls it exactly once for this document, so `+ 1` is the
    /// value the host is about to publish.
    private func noteLocalEdit() {
        onEditApplied?(documentId)
        seenEpoch += 1
    }

    /// Shared op runner: set busy, run, adopt the returned chain, re-render the
    /// edited preview (forcing the toggle on so the user sees the result), then
    /// clear busy. Errors surface to `errorMessage`.
    private func runOp(_ body: @escaping (ImageEditingService) async throws -> ImageEditChain) async {
        guard let service, !documentId.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            chain = try await body(service)
            noteLocalEdit()
            showEdited = true
            await reloadPreviews(forceOriginalReload: false, forceEditedReload: true)
        } catch {
            logger.error("operation failed: \(error.localizedDescription)")
            errorMessage = error.localizedDescription
        }
    }
}
