import SwiftUI

// MARK: - Doc×Step Grid + Timing Card

extension ActivityOverviewView {

    // MARK: Doc×Step Grid

    @ViewBuilder
    // swiftlint:disable:next function_body_length
    func docStepGrid(_ execution: WorkflowExecution) -> some View {
        let docs = execution.orderedDocumentProgress
        let stepNames = Array(Set(docs.flatMap { Array($0.stepStatuses.keys) })).sorted()

        VStack(alignment: .leading, spacing: 6) {
            Text("Files × Steps")
                .font(.subheadline.bold())
                .foregroundStyle(.secondary)

            if stepNames.isEmpty {
                Text("No step data yet")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
            } else {
                ScrollView(.horizontal, showsIndicators: false) {
                    LazyVStack(alignment: .leading, spacing: 0) {
                        // Header row
                        HStack(spacing: 0) {
                            Text("Document")
                                .font(.caption2.bold())
                                .foregroundStyle(.secondary)
                                .frame(width: 140, alignment: .leading)
                            ForEach(stepNames, id: \.self) { step in
                                Text(step)
                                    .font(.caption2.bold())
                                    .foregroundStyle(.secondary)
                                    .lineLimit(1)
                                    .frame(width: 44)
                            }
                        }
                        .padding(.bottom, 4)

                        Divider()

                        // Document rows
                        ForEach(docs) { doc in
                            HStack(spacing: 0) {
                                Text(doc.documentName)
                                    .font(.caption)
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                    .frame(width: 140, alignment: .leading)
                                ForEach(stepNames, id: \.self) { step in
                                    stepCell(doc.stepStatuses[step])
                                        .frame(width: 44)
                                }
                            }
                            .padding(.vertical, 2)
                        }

                        if docs.count > 20 {
                            Text("+ \(docs.count - 20) more")
                                .font(.caption2)
                                .foregroundStyle(.tertiary)
                                .padding(.top, 4)
                        }
                    }
                }
            }
        }
    }

    @ViewBuilder
    func stepCell(_ status: StepStatus?) -> some View {
        switch status {
        case .none, .pending:
            Image(systemName: "circle")
                .foregroundStyle(.tertiary)
                .font(.caption)
        case .running:
            ProgressView()
                .scaleEffect(0.5)
                .frame(width: 16, height: 16)
        case .completed(_, let cached):
            Image(systemName: cached ? "bolt.circle.fill" : "checkmark.circle.fill")
                .foregroundStyle(cached ? .blue : .green)
                .font(.caption)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundStyle(.red)
                .font(.caption)
        }
    }

    // MARK: Timing Stats Card

    @ViewBuilder
    func timingStatsCard(_ execution: WorkflowExecution) -> some View {
        let stats = stepTimingStats(execution)
        let stepNames = Array(stats.durations.keys).sorted()
        if !stepNames.isEmpty {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    Text("Timing")
                        .font(.headline)
                }

                Divider()

                ForEach(stepNames, id: \.self) { step in
                    timingRow(step: step, durations: stats.durations[step] ?? [], errors: stats.errors[step] ?? 0)
                }
            }
            .padding()
            .background(.regularMaterial, in: RoundedRectangle(cornerRadius: 8))
        }
    }

    @ViewBuilder
    private func timingRow(step: String, durations: [Double], errors: Int) -> some View {
        let avg = durations.reduce(0, +) / Double(durations.count)
        HStack {
            Text(step)
                .font(.caption)
            Spacer()
            if errors > 0 {
                Text("\(errors) err")
                    .font(.caption2)
                    .foregroundStyle(.red)
            }
            Text("avg \(ActivityViewHelpers.formatDuration(avg))")
                .font(.caption.monospacedDigit())
                .foregroundStyle(.secondary)
        }
    }

    // Imperative loop — must live outside @ViewBuilder
    private func stepTimingStats(
        _ execution: WorkflowExecution
    ) -> (durations: [String: [Double]], errors: [String: Int]) {
        var durations: [String: [Double]] = [:]
        var errors: [String: Int] = [:]
        for doc in execution.orderedDocumentProgress {
            for (step, status) in doc.stepStatuses {
                switch status {
                case .completed(let dur, _):
                    if let dur { durations[step, default: []].append(dur) }
                case .failed:
                    errors[step, default: 0] += 1
                default:
                    break
                }
            }
        }
        return (durations, errors)
    }
}
