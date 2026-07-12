import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for workflow batch runs (#3536). The single endpoint
/// accessor for batches — views observe `batches` and dispatch the actions
/// below; the store owns the fetch/create via `BatchServiceGenerated`.
///
/// The headline capability: run one workflow across many folders SEPARATELY —
/// one batch item per folder (each scoped to that folder's documents via
/// `selected_doc_ids`), so each folder is its own run tracked in Activity.
@MainActor
@Observable
final class BatchStore {
    private(set) var batches: [Components.Schemas.BatchResponse] = []
    private(set) var isLoading = false
    private(set) var lastError: String?

    private let batchService: BatchServiceGenerated
    private let log = Logger(subsystem: "app.fichero.fichero", category: "BatchStore")

    init(batchService: BatchServiceGenerated) {
        self.batchService = batchService
    }

    /// Load recent batches.
    func load() async {
        isLoading = true
        defer { isLoading = false }
        do {
            batches = try await batchService.listBatches()
            lastError = nil
        } catch {
            lastError = error.localizedDescription
            log.error("batch list failed: \(error.localizedDescription)")
        }
    }

    /// Run `workflowId` across `folders` — ONE batch, one item per folder (each
    /// item scoped to that folder's document ids), then execute it. Each folder
    /// becomes a separate run that surfaces in Activity. Returns the created
    /// batch, or nil on failure.
    @discardableResult
    func runFolderBatch(
        workflowId: String,
        folders: [(id: String, documentIds: [String])]
    ) async -> Components.Schemas.BatchResponse? {
        let items: [[String: any Sendable]] = folders.map { folder in
            ["selected_doc_ids": folder.documentIds]
        }
        do {
            let batch = try await batchService.createBatch(workflowId: workflowId, items: items)
            try await batchService.executeBatch(batchId: batch.batchId)
            await load()
            lastError = nil
            return batch
        } catch {
            lastError = error.localizedDescription
            log.error("batch run failed: \(error.localizedDescription)")
            return nil
        }
    }

    /// Cancel-safe delete of a batch.
    func delete(batchId: String) async {
        do {
            try await batchService.deleteBatch(batchId: batchId)
            batches.removeAll { $0.batchId == batchId }
        } catch {
            lastError = error.localizedDescription
        }
    }
}
