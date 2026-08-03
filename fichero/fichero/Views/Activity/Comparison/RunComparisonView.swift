import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "RunComparisonView")

/// Two runs of the same input, diffed where they disagree (#4341, EPIC #4312).
///
/// Deliberately has NO "run both now" button. Executing a workflow already
/// works through the existing surfaces, and burying a doubled spend inside a
/// single click is exactly the surprise this view exists to avoid. Comparing
/// two runs that already exist is free; what costs is producing the second
/// run, which is what `cost_notice` says — in the server's own words, in
/// plain sight, never behind a disclosure or inside a button label.
struct RunComparisonView: View {
    let leftThreadId: String

    @Environment(APIClient.self) private var apiClient: APIClient?

    @State private var candidates: [ExecutionThread] = []
    @State private var rightThreadId: String?
    @State private var comparison: RunComparison?
    @State private var isComparing = false
    @State private var loadError: String?
    /// Kept after the first comparison so the notice stays on screen while
    /// the user lines up the next one.
    @State private var lastCostNotice: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                picker
                if let costNotice = comparison?.costNotice ?? lastCostNotice, !costNotice.isEmpty {
                    RunComparisonCostNotice(text: costNotice)
                }
                if let loadError {
                    Label(loadError, systemImage: "exclamationmark.triangle.fill")
                        .font(.callout)
                        .foregroundStyle(.red)
                }
                if let comparison {
                    verdict(comparison)
                    RunComparisonSidesView(left: comparison.left, right: comparison.right)
                    differences(comparison)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .task(id: leftThreadId) { await loadCandidates() }
    }

    // MARK: - Choosing the other run

    @ViewBuilder
    private var picker: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Compare with another run")
                .font(.headline)
            if candidates.isEmpty {
                Text("No other run of this workflow has been recorded yet.")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            } else {
                HStack {
                    Picker("Other run", selection: $rightThreadId) {
                        Text("Choose…").tag(String?.none)
                        ForEach(candidates) { thread in
                            Text(label(for: thread)).tag(String?.some(thread.threadId))
                        }
                    }
                    .labelsHidden()
                    if isComparing {
                        ProgressView().controlSize(.small)
                    } else {
                        Button("Compare") { Task { await compare() } }
                            .disabled(rightThreadId == nil || apiClient == nil)
                    }
                }
            }
        }
    }

    private func label(for thread: ExecutionThread) -> String {
        "\(thread.workflowName) — \(thread.status.rawValue) (\(thread.threadId.prefix(8)))"
    }

    // MARK: - Verdict

    /// `comparable` is read BEFORE `identical`. Two runs that both failed are
    /// not "identical" in any sense the reader cares about, and saying so
    /// would be the same lie as a green tick over an empty step.
    @ViewBuilder
    private func verdict(_ comparison: RunComparison) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            if !comparison.comparable {
                Label(
                    comparison.incomparableReason ?? "These runs cannot be compared.",
                    systemImage: "questionmark.circle.fill"
                )
                .font(.headline)
                .foregroundStyle(.orange)
            } else if comparison.identical == true {
                Label("The two runs produced identical output.", systemImage: "equal.circle.fill")
                    .font(.headline)
                    .foregroundStyle(.green)
            } else {
                Label(
                    "\(comparison.differenceCount.formatted()) difference(s) between the two runs.",
                    systemImage: "arrow.left.arrow.right.circle.fill"
                )
                .font(.headline)
                .foregroundStyle(.blue)
            }

            // A difference means nothing if the two runs read different
            // documents, so this qualifies everything below it.
            if comparison.sameInput == false {
                Label(
                    comparison.inputNote.isEmpty
                        ? "These runs did not resolve to the same documents."
                        : comparison.inputNote,
                    systemImage: "doc.on.doc"
                )
                .font(.callout)
                .foregroundStyle(.orange)
            } else if !comparison.inputNote.isEmpty {
                Text(comparison.inputNote)
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Differences

    @ViewBuilder
    private func differences(_ comparison: RunComparison) -> some View {
        ForEach(comparison.compared) { item in
            RunArtifactComparisonRow(comparison: item)
        }
        if !comparison.onlyLeft.isEmpty {
            RunComparisonOrphanList(
                title: "Only in the first run",
                orphans: comparison.onlyLeft
            )
        }
        if !comparison.onlyRight.isEmpty {
            RunComparisonOrphanList(
                title: "Only in the second run",
                orphans: comparison.onlyRight
            )
        }
    }

    // MARK: - Loading

    private func loadCandidates() async {
        guard let apiClient else { return }
        do {
            let service = WorkflowExecutionService(libraryPath: apiClient.currentLibraryPath)
            let all = try await service.listThreads()
            let mine = all.first { $0.threadId == leftThreadId }
            candidates = all.filter {
                $0.threadId != leftThreadId && $0.workflowId == mine?.workflowId
            }
        } catch {
            logger.error("Failed to list comparison candidates: \(String(describing: error))")
            loadError = error.localizedDescription
        }
    }

    private func compare() async {
        guard let apiClient, let rightThreadId else { return }
        isComparing = true
        defer { isComparing = false }
        do {
            let result = try await ActivityService(apiClient: apiClient)
                .compareRuns(left: leftThreadId, right: rightThreadId)
            comparison = result
            lastCostNotice = result.costNotice
            loadError = nil
        } catch {
            logger.error("Comparison failed: \(String(describing: error))")
            loadError = error.localizedDescription
        }
    }
}

/// Sheet wrapper so any surface holding a thread id can open the comparison.
struct RunComparisonSheet: View {
    let threadId: String
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            RunComparisonView(leftThreadId: threadId)
                .navigationTitle("Compare Runs")
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) {
                        Button("Done") { dismiss() }
                    }
                }
        }
        .frame(minWidth: 620, minHeight: 480)
    }
}
