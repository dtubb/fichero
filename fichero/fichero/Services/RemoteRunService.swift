import FicheroAPIClient
import Foundation
import Observation

/// A run sent to a cluster or Hugging Face Jobs, as Activity's Inspector reads it (`activity.remote-under-its-step`,
/// #5740): where it runs, how far, each shard, estimate against actual. Cancel, Retry failed shards and Catch up act on
/// the same run (`/api/reading-at-scale/jobs/{id}`).
@MainActor
@Observable
final class RemoteRunService {
    struct Shard: Identifiable, Equatable {
        let id: Int
        let state: String
        let why: String?
        let lastLines: [String]
        let seconds: Double?
    }

    struct Run: Equatable {
        let target: String
        let farState: String
        let shardsDone: Int
        let shardsTotal: Int
        let pagesLanded: Int
        let shards: [Shard]
        let estimateGpuHours: Double?
        let actualSecondsPerShard: Double?
        enum Offer: Equatable { case cancel, retryFailedShards, catchUp }
        var offers: [Offer] {
            switch farState {
            case "queued", "running": return [.cancel, .catchUp]
            case "failed": return [.retryFailedShards]
            default: return []
            }
        }
    }

    private let client: FicheroClient
    private(set) var run: Run?
    private(set) var message: String?

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    func load(jobId: String) async {
        guard let response = try? await client.api.readingJobStatusApiReadingAtScaleJobsJobIdGet(path: .init(jobId: jobId)),
              case .ok(let success) = response, let body = try? success.body.json
        else { return }
        run = Run(
            target: body.target ?? "", farState: body.farState ?? "queued", shardsDone: body.shardsDone ?? 0,
            shardsTotal: body.shardsTotal ?? 0, pagesLanded: body.pagesLanded ?? 0,
            shards: (body.shards ?? []).compactMap { Self.shard(from: $0.additionalProperties.value.compactMapValues { $0 }) },
            estimateGpuHours: body.estimate?.additionalProperties.value["gpu_hours"] as? Double,
            actualSecondsPerShard: body.actual?.additionalProperties.value["seconds_per_shard"] as? Double)
    }

    private static func shard(from raw: [String: Any]?) -> Shard? {
        guard let raw, let id = raw["shard"] as? Int, let state = raw["state"] as? String else { return nil }
        return Shard(id: id, state: state, why: raw["why"] as? String,
                     lastLines: raw["last_lines"] as? [String] ?? [], seconds: raw["seconds"] as? Double)
    }

    func cancel(jobId: String) async {
        _ = try? await client.api.cancelReadingJobApiReadingAtScaleJobsJobIdCancelPost(path: .init(jobId: jobId))
        await load(jobId: jobId)
    }

    func retryFailed(jobId: String) async {
        _ = try? await client.api.resendFailedShardsApiReadingAtScaleJobsJobIdResendFailedPost(path: .init(jobId: jobId))
        await load(jobId: jobId)
    }

    func catchUp(jobId: String) async {
        _ = try? await client.api.catchUpReadingJobApiReadingAtScaleJobsJobIdCatchUpPost(path: .init(jobId: jobId))
        await load(jobId: jobId)
    }

    #if DEBUG
    /// Previews only: a service already holding a run.
    func showForPreview(_ run: Run) { self.run = run }

    /// A previewed service already holding a run: one expression for the `#Preview` body.
    static func previewing(_ run: Run, in appState: AppState) -> RemoteRunService {
        let service = appState.remoteRunService
        service.showForPreview(run)
        return service
    }
    #endif
}
