#if canImport(AppKit)
import AppKit
#elseif canImport(UIKit)
import UIKit
#endif
import Observation
import Foundation
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ImageEditorModel")

/// View-model for the non-destructive image editor (#469).
///
/// Owns the `ImageEditingServiceGenerated` and all async state so the view
/// stays declarative. Every mutating op follows the same shape: run the
/// backend op, refresh the chain, then re-render the *edited* preview so the
/// canvas reflects the new chain immediately.
@MainActor
@Observable
final class ImageEditorModel {
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

    /// Called after every successful edit or reset so the caller can evict
    /// stale storage-display caches for the affected document. Set from
    /// `ImageEditorView` once the view is configured.
    var onEditApplied: ((String) -> Void)?

    private var service: ImageEditingServiceGenerated?
    private(set) var documentId: String = ""

    /// In-flight original↔edited toggle. Tracked so rapid taps coalesce to the
    /// latest intended state instead of running out of order (#1508).
    private var toggleTask: Task<Void, Never>?

    init(documentId: String = "") {
        self.documentId = documentId
        self.chain = ImageEditChain(documentId: documentId, operations: [], updatedAt: nil)
    }

    /// Bind to a document. Safe to call repeatedly (e.g. on prev/next nav) —
    /// rebuilds state for the new document and reloads chain + preview.
    func configure(apiClient: APIClient, documentId: String, page: Int = 1) async {
        if service == nil {
            service = ImageEditingServiceGenerated(apiClient: apiClient)
        }
        self.documentId = documentId
        self.page = page
        self.chain = ImageEditChain(documentId: documentId, operations: [], updatedAt: nil)
        self.preview = nil
        self.originalPreview = nil
        self.editedPreview = nil
        await reload()
    }

    /// Reload both the chain and the current preview.
    func reload() async {
        await loadChain()
        await reloadPreviews()
    }

    private func loadChain() async {
        guard let service, !documentId.isEmpty else { return }
        do {
            chain = try await service.getChain(documentId: documentId)
        } catch {
            logger.error("getChain failed: \(error.localizedDescription)")
            // A missing chain is not an error worth surfacing — treat as empty.
            chain = ImageEditChain(documentId: documentId, operations: [], updatedAt: nil)
        }
    }

    /// Re-fetch the preview honouring the current `showEdited` toggle + page.
    func reloadPreviews() async {
        guard let service, !documentId.isEmpty else { return }
        do {
            async let original = service.loadPreview(
                documentId: documentId,
                applyEdits: false,
                page: page
            )
            async let edited = service.loadPreview(
                documentId: documentId,
                applyEdits: true,
                page: page
            )
            originalPreview = try await original
            editedPreview = try await edited
            preview = showEdited ? editedPreview : originalPreview
        } catch {
            logger.error("loadPreview failed: \(error.localizedDescription)")
            errorMessage = error.localizedDescription
        }
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
                await self.reloadPreviews()
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

    func removeOperation(at index: Int) async {
        await runOp { service in try await service.removeOperation(documentId: self.documentId, at: index) }
    }

    /// Apply the same op across many documents (#1265 batch-apply).
    ///
    /// There is no backend batch endpoint, so this fans out client-side over
    /// the per-document op endpoints. Failures on individual documents are
    /// collected rather than aborting the whole batch; the active document's
    /// chain + preview are refreshed at the end.
    func batchApply(
        documentIds: [String],
        operation: @escaping (ImageEditingServiceGenerated, String) async throws -> Void
    ) async {
        guard let service, !documentIds.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        var failures = 0
        for id in documentIds {
            do {
                try await operation(service, id)
                onEditApplied?(id)
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
            onEditApplied?(documentId)
            await reloadPreviews()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    /// Shared op runner: set busy, run, adopt the returned chain, re-render the
    /// edited preview (forcing the toggle on so the user sees the result), then
    /// clear busy. Errors surface to `errorMessage`.
    private func runOp(_ body: @escaping (ImageEditingServiceGenerated) async throws -> ImageEditChain) async {
        guard let service, !documentId.isEmpty else { return }
        isBusy = true
        defer { isBusy = false }
        do {
            chain = try await body(service)
            onEditApplied?(documentId)
            showEdited = true
            await reloadPreviews()
        } catch {
            logger.error("operation failed: \(error.localizedDescription)")
            errorMessage = error.localizedDescription
        }
    }
}
