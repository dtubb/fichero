import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "NodeComparisonSheet")

/// Sheet opened from NodePopover → "Compare Models…"
/// Runs a saved workflow's node across multiple models side-by-side and
/// lets the user pick which model to write back to the node setting.
struct NodeComparisonSheet: View {
    let workflowId: String
    let node: WorkflowNode
    /// Called when user taps "Apply" on a winning model
    let onApply: (String, String) -> Void

    @State private var store = ModelComparisonStore()

    @State private var selectedModelIds: Set<String> = []
    @State private var pinnedText: String = ""
    @State private var isRunning = false
    @State private var result: NodeComparisonResponse?
    @State private var errorMessage: String?

    @Environment(\.dismiss) private var dismiss

    private var canRun: Bool {
        selectedModelIds.count >= 2 && !isRunning
    }

    var body: some View {
        VStack(spacing: 0) {
            toolbar
            Divider()

            if let result {
                resultGrid(result)
            } else {
                configPane
            }
        }
        .frame(minWidth: 700, minHeight: 500)
        .task {
            await store.loadModels()
        }
    }

    // MARK: - Toolbar

    private var toolbar: some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Compare Models — \(node.label ?? node.tool)")
                    .font(.headline)
                Text("Run node \(node.tool) across selected models, then apply the best one")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            if result != nil {
                Button("New Comparison") {
                    self.result = nil
                    selectedModelIds = []
                }
                .buttonStyle(.bordered)
            }
            Button("Close") { dismiss() }
                .buttonStyle(.bordered)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 10)
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Config Pane (model selection + optional input)

    private var configPane: some View {
        VStack(alignment: .leading, spacing: 0) {
            modelPickerSection
            Divider()
            pinnedInputSection
            Divider()
            runButton
        }
    }

    private var modelPickerSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Select models to compare (\(selectedModelIds.count) selected)")
                    .font(.subheadline.weight(.medium))
                Spacer()
                Text("Pick 2 or more")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            if store.availableModels.isEmpty {
                ProgressView("Loading models…")
                    .frame(maxWidth: .infinity)
            } else {
                ScrollView {
                    LazyVGrid(
                        columns: [GridItem(.adaptive(minimum: 200))],
                        spacing: 6
                    ) {
                        ForEach(store.availableModels) { model in
                            modelToggle(model)
                        }
                    }
                }
                .frame(maxHeight: 240)
            }
        }
        .padding()
    }

    private func modelToggle(_ model: ComparisonModelInfo) -> some View {
        let isOn = selectedModelIds.contains(model.id)
        return Button {
            if isOn { selectedModelIds.remove(model.id) } else { selectedModelIds.insert(model.id) }
        } label: {
            HStack(spacing: 8) {
                Image(systemName: isOn ? "checkmark.circle.fill" : "circle")
                    .foregroundStyle(isOn ? Color.accentColor : Color.secondary)
                VStack(alignment: .leading, spacing: 2) {
                    Text(model.model)
                        .font(.caption.weight(.medium))
                        .lineLimit(1)
                    Text(model.provider)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Spacer()
            }
            .padding(8)
            .background(
                RoundedRectangle(cornerRadius: 6)
                    .fill(isOn ? Color.accentColor.opacity(0.12) : Color(platformColor: .platformQuaternaryLabel).opacity(0.1))
            )
        }
        .buttonStyle(.plain)
    }

    private var pinnedInputSection: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Optional test input (text)")
                .font(.subheadline.weight(.medium))
            Text("Pin a text value to pass as the node's primary input during this test run.")
                .font(.caption)
                .foregroundStyle(.secondary)

            TextField("Paste sample text here…", text: $pinnedText, axis: .vertical)
                .lineLimit(4...8)
                .textFieldStyle(.roundedBorder)
                .font(.caption)
        }
        .padding()
    }

    private var runButton: some View {
        HStack {
            if let err = errorMessage {
                Text(err)
                    .font(.caption)
                    .foregroundStyle(.red)
                    .lineLimit(2)
            }
            Spacer()
            Button {
                Task { await runComparison() }
            } label: {
                if isRunning {
                    ProgressView().controlSize(.small)
                } else {
                    Label("Run Comparison", systemImage: "play.fill")
                }
            }
            .buttonStyle(.borderedProminent)
            .disabled(!canRun)
        }
        .padding()
    }

    // MARK: - Result Grid

    @ViewBuilder
    private func resultGrid(_ response: NodeComparisonResponse) -> some View {
        ScrollView(.horizontal, showsIndicators: true) {
            HStack(alignment: .top, spacing: 1) {
                ForEach(response.choices) { choice in
                    NodeResultCard(
                        choice: choice,
                        isCurrent: choice.provider == node.providerName && choice.model == node.modelName
                    ) {
                        onApply(choice.provider, choice.model)
                        dismiss()
                    }
                }
            }
        }
        .background(Color(.separatorColor))
    }

    // MARK: - Run

    private func runComparison() async {
        errorMessage = nil
        isRunning = true
        defer { isRunning = false }

        let modelSpecs = store.availableModels
            .filter { selectedModelIds.contains($0.id) }
            .map { ModelSpec(provider: $0.provider, model: $0.model) }

        var pinned: [String: String] = [:]
        if !pinnedText.isEmpty {
            pinned["text"] = pinnedText
        }

        do {
            result = try await store.compareNode(
                workflowId: workflowId,
                nodeId: node.id,
                models: modelSpecs,
                pinnedInputs: pinned
            )
            logger.info("Node comparison complete for node \(node.id)")
        } catch {
            errorMessage = error.localizedDescription
            logger.error("Node comparison failed: \(error.localizedDescription)")
        }
    }
}

// MARK: - NodeResultCard

private struct NodeResultCard: View {
    let choice: NodeComparisonChoice
    let isCurrent: Bool
    let onApply: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            cardHeader
            Divider()
            if let err = choice.result.error {
                errorBody(err)
            } else {
                responseBody
            }
            Divider()
            cardFooter
        }
        .frame(minWidth: 280, maxWidth: 400)
        .background(Color(.windowBackgroundColor))
    }

    private var cardHeader: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack {
                Text(choice.model)
                    .font(.subheadline.weight(.semibold))
                    .lineLimit(1)
                if isCurrent {
                    Text("current")
                        .font(.caption2)
                        .padding(.horizontal, 5)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.15))
                        .cornerRadius(4)
                }
                Spacer()
            }
            Text(choice.provider)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .padding(10)
    }

    private var responseBody: some View {
        ScrollView {
            Text(choice.result.response)
                .font(.caption)
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
                .padding(10)
        }
        .frame(minHeight: 200, maxHeight: 400)
    }

    private func errorBody(_ message: String) -> some View {
        Text(message)
            .font(.caption)
            .foregroundStyle(.red)
            .padding(10)
            .frame(minHeight: 80, maxHeight: 200)
    }

    private var cardFooter: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text(String(format: "%.0f ms", choice.result.latencyMs))
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(String(format: "$%.5f", choice.result.costUsd))
                    .font(.caption2)
                    .foregroundStyle(.green)
            }
            Spacer()
            if !isCurrent {
                Button("Apply") { onApply() }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
        .padding(10)
    }
}
