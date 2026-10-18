import SwiftUI

/// The Inspector of a run sent to a cluster or Hugging Face Jobs: target and far-side state, shards done of total,
/// pages landed, estimate against actual, each shard with its reason, and what the row offers.
struct RemoteRunInspector: View {
    let jobId: String
    @State var service: RemoteRunService

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let run = service.run {
                Text("\(run.target) · \(run.farState) · \(run.shardsDone) of \(run.shardsTotal) shards · \(run.pagesLanded) pages landed")
                    .font(.callout)
                if run.estimateGpuHours != nil || run.actualSecondsPerShard != nil {
                    Text(estimateWords(run)).font(.caption).foregroundStyle(.secondary)
                }
                ForEach(run.shards) { shard in
                    VStack(alignment: .leading, spacing: 2) {
                        Text("Shard \(shard.id): \(shard.state)").font(.caption)
                        if let why = shard.why { Text(why).font(.caption).foregroundStyle(.orange) }
                        ForEach(shard.lastLines.suffix(3), id: \.self) { line in
                            Text(line).font(.caption.monospaced()).foregroundStyle(.secondary)
                        }
                    }
                }
                HStack {
                    if run.offers.contains("Cancel") { Button("Cancel") { Task { await service.cancel(jobId: jobId) } } }
                    if run.offers.contains("Retry failed shards") {
                        Button("Retry failed shards") { Task { await service.retryFailed(jobId: jobId) } }
                    }
                    if run.offers.contains("Catch up") { Button("Catch up") { Task { await service.catchUp(jobId: jobId) } } }
                }
                .controlSize(.small)
            }
        }
        .task { await service.load(jobId: jobId) }
    }

    private func estimateWords(_ run: RemoteRunService.Run) -> String {
        let estimate = run.estimateGpuHours.map { String(format: "about %.1f GPU-hours expected", $0) }
        let actual = run.actualSecondsPerShard.map { String(format: "%.0f s a shard so far", $0) }
        return [estimate, actual].compactMap { $0 }.joined(separator: " · ")
    }
}

#Preview("A cluster run with one failed shard") {
    let service = AppState().remoteRunService
    service.showForPreview(.init(
        target: "Rorqual", farState: "failed", shardsDone: 18, shardsTotal: 20, pagesLanded: 900,
        shards: [.init(id: 7, state: "failed", why: "ran out of time before it finished",
                       lastLines: ["slurmstepd: error: *** JOB 4242_7 ON rc12345 CANCELLED DUE TO TIME LIMIT ***"], seconds: nil)],
        estimateGpuHours: 1.2, actualSecondsPerShard: 310))
    return RemoteRunInspector(jobId: "preview", service: service).padding().frame(width: 460)
}
