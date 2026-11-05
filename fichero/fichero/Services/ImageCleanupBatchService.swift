import FicheroAPIClient
import Foundation
import OpenAPIRuntime

/// One cleanup step the editor can copy to every page of a folder (`image.enhance.batch-preview-undo`, #6192): the engine's
/// operation name and the step's settings, as `POST /api/images/batch-apply` takes them.
struct CleanupStep: Equatable, Identifiable {
    let id: String
    let title: String
    let operation: String
    var params: [String: String] = [:]

    static let all: [CleanupStep] = [
        .init(id: "enhance", title: "Auto Enhance", operation: "enhance", params: ["method": "clahe", "profile": "handwritten"]),
        .init(id: "sharpen", title: "Sharpen", operation: "sharpen"),
        .init(id: "denoise", title: "Remove Speckle", operation: "denoise"),
        .init(id: "fuzzy_clean", title: "Clean Stains", operation: "fuzzy_clean"),
        .init(id: "binarise", title: "Black and White", operation: "binarise")
    ]
}

/// A page of the folder, as the list after Apply names it.
struct CleanupPageRef: Equatable, Identifiable {
    let id: String
    let name: String
}

/// A page's picture before and after the step, small JPEG bytes; nothing is written to make it.
struct CleanupPreviewPage: Equatable, Identifiable {
    let id: String
    let name: String
    let before: Data
    let after: Data
}

struct CleanupPreview: Equatable {
    let pages: Int
    let samples: [CleanupPreviewPage]
}

/// What the sheet needs from the engine: one preview, one apply, one undo.
protocol ImageCleanupBatching {
    func preview(folderId: String, step: CleanupStep) async throws -> CleanupPreview
    func apply(folderId: String, step: CleanupStep) async throws -> String
    func undo(batchId: String) async throws
}

struct ImageCleanupBatchService: ImageCleanupBatching {
    let apiClient: APIClient

    func preview(folderId: String, step: CleanupStep) async throws -> CleanupPreview {
        let output = try await apiClient.api.batchApplyImageOperationApiImagesBatchApplyPost(
            query: .init(preview: 3), body: .json(try request(folderId: folderId, step: step)))
        // The answer is either a batch or a preview; decode the one that is there through its own Codable shape.
        let data = try JSONEncoder().encode(try output.ok.body.json)
        let answer = try JSONDecoder().decode(Components.Schemas.BatchApplyPreview.self, from: data)
        let samples = answer.previews.compactMap { item -> CleanupPreviewPage? in
            guard let before = Data(base64Encoded: item.beforeBase64), let after = Data(base64Encoded: item.afterBase64) else { return nil }
            return CleanupPreviewPage(id: item.documentId, name: item.name, before: before, after: after)
        }
        return CleanupPreview(pages: answer.pages, samples: samples)
    }

    func apply(folderId: String, step: CleanupStep) async throws -> String {
        let output = try await apiClient.api.batchApplyImageOperationApiImagesBatchApplyPost(
            body: .json(try request(folderId: folderId, step: step)))
        let data = try JSONEncoder().encode(try output.ok.body.json)
        return try JSONDecoder().decode(Components.Schemas.BatchResponse.self, from: data).batchId
    }

    func undo(batchId: String) async throws {
        _ = try await apiClient.api.undoBatchImageOperationApiImagesBatchApplyBatchIdUndoPost(
            path: .init(batchId: batchId)).ok
    }

    private func request(folderId: String, step: CleanupStep) throws -> Components.Schemas.BatchImageApplyRequest {
        guard let operation = Components.Schemas.BatchImageApplyRequest.OperationPayload(rawValue: step.operation) else {
            throw CleanupBatchError.unknownStep(step.operation)
        }
        let settings = try OpenAPIObjectContainer(unvalidatedValue: step.params)
        return .init(folderId: folderId, operation: operation, params: .init(additionalProperties: settings))
    }
}

enum CleanupBatchError: Error, Equatable { case unknownStep(String) }
