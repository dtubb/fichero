import AppKit
import Foundation
import OSLog
import SwiftUI

private let logger = Logger(subsystem: "com.fichero.fichero", category: "ImageEditorModel")

/// View-model for the non-destructive image editor (#469).
///
/// Owns the `ImageEditingServiceGenerated` and all async state so the view
/// stays declarative. Every mutating op follows the same shape: run the
/// backend op, refresh the chain, then re-render the *edited* preview so the
/// canvas reflects the new chain immediately.
@MainActor
final class ImageEditorModel: ObservableObject {
    /// Currently displayed preview (original or edited, per `showEdited`).
    @Published var preview: PreviewImage?
    /// The document's saved edit chain.
    @Published var chain: ImageEditChain
    /// #469 toggle — false shows the untouched source, true shows the chain applied.
    @Published var showEdited: Bool = true
    /// 1-indexed page (PDF documents); always 1 for single images.
    @Published var page: Int = 1
    /// True while any op / load is in flight (drives the busy overlay + disables controls).
    @Published var isBusy: Bool = false
    @Published var errorMessage: String?

    private var service: ImageEditingServiceGenerated?
    private(set) var documentId: String = ""

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
        await reload()
    }

    /// Reload both the chain and the current preview.
    func reload() async {
        await loadChain()
        await reloadPreview()
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
    func reloadPreview() async {
        guard let service, !documentId.isEmpty else { return }
        do {
            preview = try await service.loadPreview(
                documentId: documentId,
                applyEdits: showEdited,
                page: page
            )
        } catch {
            logger.error("loadPreview failed: \(error.localizedDescription)")
            errorMessage = error.localizedDescription
        }
    }

    /// Flip the original↔edited toggle and re-render (#469).
    func toggleEdited() {
        showEdited.toggle()
        Task { await reloadPreview() }
    }

    // MARK: - Operations

    func rotate(by degrees: Double) async {
        await runOp { service in
            try await service.rotate(documentId: self.documentId, angle: degrees, page: self.page)
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
            await reloadPreview()
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
            showEdited = true
            await reloadPreview()
        } catch {
            logger.error("operation failed: \(error.localizedDescription)")
            errorMessage = error.localizedDescription
        }
    }
}
