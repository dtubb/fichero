import SwiftUI

/// The Inspector of a run sent to a cluster or Hugging Face Jobs: target and far-side state, shards done of total,
/// pages landed, estimate against actual, each shard with its reason, and what the row offers.
struct RemoteRunInspector: View {
    let jobId: String
    @State var service: RemoteRunService

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("On the Cluster").font(.headline)
            if let run = service.run {
                card(run)
            } else {
                ProgressView().controlSize(.small)
            }
        }
        .accessibilityIdentifier("activity.details.remote")
        .task { await service.load(jobId: jobId) }
    }

    private func card(_ run: RemoteRunService.Run) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Image(systemName: Self.symbol(run.farState)).foregroundStyle(Self.tint(run.farState))
                Text(run.target).font(.body.weight(.semibold))
                Spacer()
                Text(Self.words(run.farState))
                    .font(.caption.weight(.medium))
                    .foregroundStyle(Self.tint(run.farState))
            }
            if run.shardsTotal > 0 {
                ProgressView(value: Double(min(run.shardsDone, run.shardsTotal)), total: Double(run.shardsTotal)) {
                    EmptyView()
                } currentValueLabel: {
                    Text("\(run.shardsDone) of \(run.shardsTotal) shards").monospacedDigit()
                }
                .controlSize(.small)
                .tint(run.farState == "failed" ? .red : .accentColor)
            }
            Text("\(run.pagesLanded) pages landed").font(.callout)
            if run.estimateGpuHours != nil || run.actualSecondsPerShard != nil {
                Text(estimateWords(run)).font(.callout).foregroundStyle(.secondary)
            }
            ForEach(run.shards.filter { $0.why != nil }) { shard in
                Label("Shard \(shard.id): \(shard.why ?? "")", systemImage: "exclamationmark.triangle")
                    .font(.callout)
                    .foregroundStyle(.orange)
                    .textSelection(.enabled)
            }
            HStack {
                ForEach(run.offers, id: \.self) { offer in
                    switch offer {
                    case .cancel:
                        Button("Cancel", role: .destructive) { Task { await service.cancel(jobId: jobId) } }
                            .accessibilityIdentifier("activity.details.remote.cancel")
                    case .retryFailedShards:
                        Button("Retry Failed Shards") { Task { await service.retryFailed(jobId: jobId) } }
                            .accessibilityIdentifier("activity.details.remote.retry")
                    case .catchUp:
                        Button("Catch Up") { Task { await service.catchUp(jobId: jobId) } }
                            .accessibilityIdentifier("activity.details.remote.catchUp")
                    }
                }
            }
            .controlSize(.small)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.secondary.opacity(0.08)))
        .accessibilityElement(children: .contain)
    }

    static func words(_ farState: String) -> String {
        switch farState {
        case "queued": "Waiting in the queue"
        case "running": "Running"
        case "done": "Done"
        case "failed": "Failed"
        case "cancelled": "Cancelled"
        default: "Waiting"
        }
    }

    static func symbol(_ farState: String) -> String {
        switch farState {
        case "running": "play.circle.fill"
        case "done": "checkmark.circle.fill"
        case "failed": "exclamationmark.triangle.fill"
        case "cancelled": "minus.circle"
        default: "hourglass"
        }
    }

    static func tint(_ farState: String) -> Color {
        switch farState {
        case "running": .accentColor
        case "done": .green
        case "failed": .red
        default: .secondary
        }
    }

    private func estimateWords(_ run: RemoteRunService.Run) -> String {
        let estimate = run.estimateGpuHours.map { "about \($0.formatted(.number.precision(.fractionLength(1)))) GPU-hours expected" }
        let actual = run.actualSecondsPerShard.map {
            "\(Duration.seconds($0).formatted(.units(allowed: [.minutes, .seconds], width: .abbreviated))) a shard so far"
        }
        return [estimate, actual].compactMap { $0 }.joined(separator: " · ")
    }
}

#if DEBUG
#Preview("A cluster run with one failed shard") {
    let appState = AppState()
    let shard = RemoteRunService.Shard(
        id: 7, state: "failed", why: "ran out of time before it finished",
        lastLines: ["slurmstepd: error: *** JOB 4242_7 ON rc12345 CANCELLED DUE TO TIME LIMIT ***"], seconds: nil)
    let run = RemoteRunService.Run(
        target: "Rorqual", farState: "failed", shardsDone: 18, shardsTotal: 20, pagesLanded: 900, shards: [shard],
        estimateGpuHours: 1.2, actualSecondsPerShard: 310)
    RemoteRunInspector(jobId: "preview", service: RemoteRunService.previewing(run, in: appState))
        .padding()
        .frame(width: 460)
}
#endif
