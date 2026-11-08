import FicheroAPIClient
import Foundation
import OpenAPIRuntime

// A long image operation asked for as a job (`image.ops.long-operation-is-a-job`, #6384). The engine returns a job id at once and the
// images lane runs the same audited `image.<op>` action, so the request is never held open: the row is in Activity with its progress
// and its own Cancel, and the engine keeps answering health and reads. This waits on that job through the Activity job read.

enum ImageJobError: LocalizedError {
    case refused(Int)
    case failed(String)
    case stopped

    var errorDescription: String? {
        switch self {
        case .refused(let code): "The engine did not take the operation (HTTP \(code))."
        case .failed(let why): why
        case .stopped: "The operation was stopped."
        }
    }
}

extension ImageEditingService {
    /// `POST /api/images/{id}/jobs`: queue `action` (an `image.<op>`) with its settings; returns the job id.
    func queueJob(documentId: String, action: String, params: [String: (any Sendable)?]) async throws -> String {
        let container = try OpenAPIObjectContainer(unvalidatedValue: params)
        let response = try await client.api.queueImageOperationJobApiImagesDocumentIdJobsPost(
            path: .init(documentId: documentId),
            body: .json(.init(action: action, params: .init(additionalProperties: container))))
        guard case .accepted(let accepted) = response else { throw ImageJobError.refused(0) }
        return try accepted.body.json.jobId
    }

    /// Wait for the job to end, one read a second. Done returns; failed or cancelled throws with the engine's reason. If this task is
    /// cancelled while waiting, the job is cancelled with it, so closing the editor does not leave an operation running unseen.
    func waitForJob(id: String) async throws {
        while true {
            if Task.isCancelled {
                _ = try? await client.api.cancelJobApiActivityJobsJobIdCancelPost(path: .init(jobId: id))
                throw CancellationError()
            }
            if case .ok(let read) = try await client.api.getJobTreeApiActivityJobsJobIdGet(path: .init(jobId: id)) {
                let node = try read.body.json
                switch node.state {
                case "done", "completed": return
                case "cancelled": throw ImageJobError.stopped
                case "failed": throw ImageJobError.failed(node.reason.flatMap { $0.isEmpty ? nil : $0 } ?? "The operation failed.")
                default: break
                }
            }
            try? await Task.sleep(for: .seconds(1))
        }
    }

    /// Remove background as a job, then the page's edit chain as the operation left it.
    func removeBackgroundAsJob(documentId: String, method: String = "opencv", threshold: Int = 28,
                               page: Int = 1) async throws -> ImageEditChain {
        let id = try await queueJob(documentId: documentId, action: "image.remove_background",
                                    params: ["method": method, "threshold": threshold, "page": page])
        try await waitForJob(id: id)
        return try await getChain(documentId: documentId)
    }
}
