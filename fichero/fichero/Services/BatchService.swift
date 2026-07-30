import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime
import OSLog

private let logger = Logger(subsystem: "app.fichero.fichero", category: "BatchService")

/// Service for batch operations using generated OpenAPI client
/// Note: Batch endpoints are global (not library-scoped)
@MainActor
@Observable
class BatchService {
    private let client: FicheroClient

    /// Initialize with FicheroClient (preferred)
    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    // MARK: - Batch Operations

    /// List all batches
    func listBatches(status: String? = nil, limit: Int = 100) async throws -> [Components.Schemas.BatchResponse] {
        let response = try await client.api.listBatchesApiBatchesGet(
            query: .init(status: status, limit: limit)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json.items
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw BatchServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw BatchServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Create a new batch
    /// - Parameters:
    ///   - workflowId: The workflow to execute
    ///   - items: Array of input dictionaries, one per item
    ///   - maxConcurrent: Maximum concurrent executions (1-50)
    /// #4024: pure builder for the CreateBatch request body, extracted so tests can
    /// verify the encoded payload directly — the generated client sends POST bodies as
    /// URLSession upload tasks whose body is invisible to a URLProtocol stub. Production
    /// `createBatch` calls this unchanged; behavior is identical.
    static func makeCreateBatchRequest(
        workflowId: String,
        items: [[String: any Sendable]],
        maxConcurrent: Int
    ) throws -> Components.Schemas.CreateBatchRequest {
        // Each ItemsPayloadPayload wraps an OpenAPIObjectContainer in its additionalProperties.
        let itemsPayload: Components.Schemas.CreateBatchRequest.ItemsPayload = try items.map { dict in
            let container = try OpenAPIObjectContainer(unvalidatedValue: dict)
            return Components.Schemas.CreateBatchRequest.ItemsPayloadPayload(additionalProperties: container)
        }
        return Components.Schemas.CreateBatchRequest(
            workflowId: workflowId,
            items: itemsPayload,
            maxConcurrent: maxConcurrent
        )
    }

    func createBatch(
        workflowId: String,
        items: [[String: any Sendable]],
        maxConcurrent: Int = 5
    ) async throws -> Components.Schemas.BatchResponse {
        let request = try Self.makeCreateBatchRequest(
            workflowId: workflowId,
            items: items,
            maxConcurrent: maxConcurrent
        )

        let response = try await client.api.createBatchApiBatchesPost(
            body: .json(request)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw BatchServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw BatchServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get a specific batch
    func getBatch(batchId: String, includeItems: Bool = true) async throws -> Components.Schemas.BatchResponse {
        let response = try await client.api.getBatchApiBatchesBatchIdGet(
            path: .init(batchId: batchId),
            query: .init(includeItems: includeItems)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw BatchServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw BatchServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Delete a batch
    func deleteBatch(batchId: String) async throws {
        let response = try await client.api.deleteBatchApiBatchesBatchIdDelete(
            path: .init(batchId: batchId)
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw BatchServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw BatchServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Get batch progress
    func getBatchProgress(batchId: String) async throws -> Components.Schemas.BatchProgressResponse {
        let response = try await client.api.getBatchProgressApiBatchesBatchIdProgressGet(
            path: .init(batchId: batchId)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw BatchServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw BatchServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Execute a batch.
    /// The request fires and the backend runs asynchronously — poll getBatchProgress() for status.
    func executeBatch(batchId: String) async throws {
        let response = try await client.api.executeBatchApiBatchesBatchIdExecutePost(
            path: .init(batchId: batchId)
        )

        switch response {
        case .ok:
            return
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw BatchServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw BatchServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Pause a running batch
    func pauseBatch(batchId: String) async throws -> Components.Schemas.BatchResponse {
        let response = try await client.api.pauseBatchApiBatchesBatchIdPausePost(
            path: .init(batchId: batchId)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw BatchServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw BatchServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Resume a paused batch (starts SSE stream - returns immediately)
    /// Note: Use getBatchProgress() to poll for status, or use SSE streaming endpoint directly
    func resumeBatch(batchId: String) async throws {
        let response = try await client.api.resumeBatchApiBatchesBatchIdResumePost(
            path: .init(batchId: batchId)
        )

        switch response {
        case .ok:
            return  // SSE streaming started
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw BatchServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw BatchServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Cancel a batch
    func cancelBatch(batchId: String) async throws -> Components.Schemas.BatchResponse {
        let response = try await client.api.cancelBatchApiBatchesBatchIdCancelPost(
            path: .init(batchId: batchId)
        )

        switch response {
        case .ok(let okResponse):
            return try okResponse.body.json
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw BatchServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw BatchServiceError.unexpectedResponse(statusCode)
        }
    }

    /// Retry failed items in a batch (starts SSE stream - returns immediately)
    /// Note: Use getBatchProgress() to poll for status, or use SSE streaming endpoint directly
    func retryBatch(batchId: String) async throws {
        let response = try await client.api.retryBatchApiBatchesBatchIdRetryPost(
            path: .init(batchId: batchId)
        )

        switch response {
        case .ok:
            return  // SSE streaming started
        case .unprocessableContent(let error):
            let detail = try? error.body.json
            throw BatchServiceError.validationError(detail?.detail?.description ?? "Validation error")
        case .undocumented(let statusCode, _):
            throw BatchServiceError.unexpectedResponse(statusCode)
        }
    }
}

// MARK: - App Type Convenience Methods

extension BatchService {
    /// List batches returning app BatchInfo type (for backward compatibility)
    func listBatchesAsInfo(status: String? = nil, limit: Int = 100) async throws -> [BatchInfo] {
        let batches = try await listBatches(status: status, limit: limit)
        return batches.map { convertToBatchInfo($0) }
    }

    /// Get batch returning app BatchInfo type (for backward compatibility)
    func getBatchAsInfo(batchId: String, includeItems: Bool = true) async throws -> BatchInfo {
        let batch = try await getBatch(batchId: batchId, includeItems: includeItems)
        return convertToBatchInfo(batch)
    }

    /// Pause batch returning app BatchInfo type
    func pauseBatchAsInfo(batchId: String) async throws -> BatchInfo {
        let batch = try await pauseBatch(batchId: batchId)
        return convertToBatchInfo(batch)
    }

    /// Cancel batch returning app BatchInfo type
    func cancelBatchAsInfo(batchId: String) async throws -> BatchInfo {
        let batch = try await cancelBatch(batchId: batchId)
        return convertToBatchInfo(batch)
    }

    /// Convert generated BatchResponse to app BatchInfo
    private func convertToBatchInfo(
        _ response: Components.Schemas.BatchResponse
    ) -> BatchInfo {
        let items: [BatchItemInfo]? = response.items?.map { item in
            // Convert inputs from InputsPayload (which has additionalProperties:
            // OpenAPIObjectContainer) to [String: String]
            var converted: [String: String] = [:]
            if let inputsDict = item.inputs.additionalProperties.value as [String: any Sendable]? {
                for (key, value) in inputsDict {
                    if let str = value as? String {
                        converted[key] = str
                    } else {
                        converted[key] = String(describing: value)
                    }
                }
            }
            let inputsDict: [String: String]? = converted.isEmpty ? nil : converted

            return BatchItemInfo(
                threadId: item.threadId,
                itemIndex: item.itemIndex,
                inputs: inputsDict,
                status: item.status,
                error: item.error,
                startedAt: item.startedAt,
                completedAt: item.completedAt
            )
        }

        return BatchInfo(
            batchId: response.batchId,
            workflowId: response.workflowId,
            status: response.status,
            totalItems: response.totalItems,
            completedItems: response.completedItems,
            failedItems: response.failedItems,
            maxConcurrent: response.maxConcurrent,
            createdAt: response.createdAt,
            startedAt: response.startedAt,
            completedAt: response.completedAt,
            errorMessage: response.errorMessage,
            items: items
        )
    }
}

// MARK: - Error Types

enum BatchServiceError: LocalizedError {
    case validationError(String)
    case unexpectedResponse(Int)

    var errorDescription: String? {
        switch self {
        case .validationError(let message):
            return "Validation error: \(message)"
        case .unexpectedResponse(let statusCode):
            return "Unexpected response: HTTP \(statusCode)"
        }
    }
}
