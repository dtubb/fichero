import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "WorkflowChainListView")

/// View for browsing and managing workflow chains
struct WorkflowChainListView: View {
    @StateObject private var chainService: ChainService
    @EnvironmentObject var workflowStore: WorkflowStore
    @State private var searchText = ""
    @State private var selectedChainId: String?
    @State private var showNewChainSheet = false
    @State private var showDeleteConfirmation = false
    @State private var chainToDelete: WorkflowChain?
    @State private var executingChainId: String?

    init(apiClient: APIClient) {
        _chainService = StateObject(wrappedValue: ChainService(apiClient: apiClient))
    }

    var body: some View {
        chainList
            .searchable(text: $searchText, prompt: "Search chains...")
            .task {
                guard !Task.isCancelled else { return }
                await chainService.loadChains()
            }
            .sheet(isPresented: $showNewChainSheet) {
                NewChainSheet(
                    workflows: workflowStore.workflows,
                    onCreate: { name, description, steps in
                        await createChain(name: name, description: description, steps: steps)
                    }
                )
            }
            .sheet(item: selectedChain) { chain in
                ChainDetailSheet(
                    chain: chain,
                    workflows: workflowStore.workflows,
                    onExecute: { executeChain(chain) },
                    onDelete: { confirmDelete(chain) }
                )
            }
            .alert("Delete Chain?", isPresented: $showDeleteConfirmation) {
                Button("Cancel", role: .cancel) {
                    chainToDelete = nil
                }
                Button("Delete", role: .destructive) {
                    if let chain = chainToDelete {
                        Task { await deleteChain(chain) }
                    }
                }
            } message: {
                if let chain = chainToDelete {
                    Text("Are you sure you want to delete \"\(chain.name)\"? This action cannot be undone.")
                }
            }
    }

    /// Selected chain binding for sheet presentation
    private var selectedChain: Binding<WorkflowChain?> {
        Binding(
            get: {
                guard let id = selectedChainId else { return nil }
                return chainService.chains.first { $0.id == id }
            },
            set: { newChain in
                selectedChainId = newChain?.id
            }
        )
    }

    @ViewBuilder
    private var chainList: some View {
        Group {
            if chainService.isLoading && chainService.chains.isEmpty {
                ProgressView("Loading chains...")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if filteredChains.isEmpty {
                ContentUnavailableView {
                    Label("No Chains", systemImage: "link")
                } description: {
                    if searchText.isEmpty {
                        Text("Create your first chain to connect workflows together")
                    } else {
                        Text("No chains match your search")
                    }
                } actions: {
                    if searchText.isEmpty {
                        Button("New Chain") {
                            showNewChainSheet = true
                        }
                        .buttonStyle(.borderedProminent)
                    }
                }
            } else {
                List(filteredChains) { chain in
                    ChainListRow(
                        chain: chain,
                        isExecuting: executingChainId == chain.id
                    )
                    .contentShape(Rectangle())
                    .onTapGesture(count: 2) {
                        // Double-click to open details
                        selectedChainId = chain.id
                    }
                    .contextMenu {
                        Button {
                            selectedChainId = chain.id
                        } label: {
                            Label("View Details", systemImage: "info.circle")
                        }

                        Button {
                            executeChain(chain)
                        } label: {
                            Label("Execute", systemImage: "play.fill")
                        }

                        Divider()

                        Button(role: .destructive) {
                            confirmDelete(chain)
                        } label: {
                            Label("Delete", systemImage: "trash")
                        }
                    }
                }
            }
        }
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    showNewChainSheet = true
                } label: {
                    Label("New Chain", systemImage: "plus")
                }
            }

            ToolbarItem(placement: .automatic) {
                Button {
                    Task { await chainService.loadChains() }
                } label: {
                    Label("Refresh", systemImage: "arrow.clockwise")
                }
            }
        }
    }

    private var filteredChains: [WorkflowChain] {
        if searchText.isEmpty {
            return chainService.chains
        }
        return chainService.chains.filter { chain in
            chain.name.localizedCaseInsensitiveContains(searchText) ||
            chain.description.localizedCaseInsensitiveContains(searchText)
        }
    }

    // MARK: - Actions

    private func createChain(name: String, description: String, steps: [ChainStep]) async {
        do {
            _ = try await chainService.createChain(
                name: name,
                description: description,
                steps: steps
            )
            logger.info("Created chain: \(name)")
        } catch {
            logger.error("Failed to create chain: \(error.localizedDescription)")
        }
    }

    private func deleteChain(_ chain: WorkflowChain) async {
        do {
            try await chainService.deleteChain(chain.id)
            if selectedChainId == chain.id {
                selectedChainId = nil
            }
            logger.info("Deleted chain: \(chain.name)")
        } catch {
            logger.error("Failed to delete chain: \(error.localizedDescription)")
        }
    }

    private func confirmDelete(_ chain: WorkflowChain) {
        chainToDelete = chain
        showDeleteConfirmation = true
    }

    private func executeChain(_ chain: WorkflowChain) {
        executingChainId = chain.id
        Task {
            do {
                let response = try await chainService.executeChain(chainId: chain.id)
                logger.info("Started chain execution: \(response.executionId)")

                // Poll for completion
                let result = try await chainService.waitForExecution(response.executionId) { status in
                    logger.debug("Chain progress: \(status.status)")
                }

                logger.info("Chain completed with status: \(result.status)")
            } catch {
                logger.error("Chain execution failed: \(error.localizedDescription)")
            }
            executingChainId = nil
        }
    }
}

// MARK: - Chain List Row

struct ChainListRow: View {
    let chain: WorkflowChain
    let isExecuting: Bool

    var body: some View {
        HStack {
            VStack(alignment: .leading, spacing: 4) {
                HStack {
                    Text(chain.name)
                        .font(.headline)

                    if isExecuting {
                        ProgressView()
                            .controlSize(.small)
                    }
                }

                if !chain.description.isEmpty {
                    Text(chain.description)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }

                Text("\(chain.steps.count) step\(chain.steps.count == 1 ? "" : "s")")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            Spacer()

            Image(systemName: "link")
                .foregroundStyle(.secondary)
        }
        .padding(.vertical, 4)
    }
}

// MARK: - Chain Detail Sheet

/// Sheet wrapper for chain details
struct ChainDetailSheet: View {
    let chain: WorkflowChain
    let workflows: [WorkflowSidebarItem]
    let onExecute: () -> Void
    let onDelete: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        NavigationStack {
            ChainDetailContent(
                chain: chain,
                workflows: workflows,
                onExecute: onExecute,
                onDelete: {
                    dismiss()
                    onDelete()
                }
            )
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Done") { dismiss() }
                }
            }
        }
        .frame(minWidth: 500, minHeight: 400)
    }
}

// MARK: - Chain Detail Content

/// Reusable chain detail content (used in sheet and potentially elsewhere)
struct ChainDetailContent: View {
    let chain: WorkflowChain
    let workflows: [WorkflowSidebarItem]
    let onExecute: () -> Void
    let onDelete: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Header
                VStack(alignment: .leading, spacing: 8) {
                    Text(chain.name)
                        .font(.largeTitle)
                        .fontWeight(.bold)

                    if !chain.description.isEmpty {
                        Text(chain.description)
                            .font(.body)
                            .foregroundStyle(.secondary)
                    }
                }

                Divider()

                // Steps
                VStack(alignment: .leading, spacing: 12) {
                    Text("Steps")
                        .font(.headline)

                    if chain.steps.isEmpty {
                        Text("No steps defined")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(Array(chain.steps.enumerated()), id: \.element.id) { index, step in
                            ChainStepRow(
                                step: step,
                                index: index,
                                workflowName: workflowName(for: step.workflowId)
                            )
                        }
                    }
                }

                Divider()

                // Actions
                HStack(spacing: 16) {
                    Button {
                        onExecute()
                    } label: {
                        Label("Execute Chain", systemImage: "play.fill")
                    }
                    .buttonStyle(.borderedProminent)

                    Button(role: .destructive) {
                        onDelete()
                    } label: {
                        Label("Delete", systemImage: "trash")
                    }
                }
            }
            .padding()
        }
        .navigationTitle(chain.name)
    }

    private func workflowName(for id: String) -> String {
        workflows.first { $0.id == id }?.name ?? "Unknown Workflow"
    }
}

// MARK: - Chain Step Row

struct ChainStepRow: View {
    let step: ChainStep
    let index: Int
    let workflowName: String

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Step number
            ZStack {
                Circle()
                    .fill(.blue.opacity(0.2))
                    .frame(width: 32, height: 32)

                Text("\(index + 1)")
                    .font(.headline)
                    .foregroundStyle(.blue)
            }

            // Step details
            VStack(alignment: .leading, spacing: 4) {
                Text(step.name.isEmpty ? "Step \(index + 1)" : step.name)
                    .font(.headline)

                HStack {
                    Image(systemName: "flowchart")
                        .foregroundStyle(.secondary)
                    Text(workflowName)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)
                }

                if !step.inputMappings.isEmpty {
                    HStack {
                        Image(systemName: "arrow.right.circle")
                            .foregroundStyle(.tertiary)
                        Text("\(step.inputMappings.count) input mapping\(step.inputMappings.count == 1 ? "" : "s")")
                            .font(.caption)
                            .foregroundStyle(.tertiary)
                    }
                }

                if step.condition != nil {
                    HStack {
                        Image(systemName: "questionmark.diamond")
                            .foregroundStyle(.orange)
                        Text("Conditional")
                            .font(.caption)
                            .foregroundStyle(.orange)
                    }
                }
            }

            Spacer()

            // Timeout indicator
            if step.timeoutSeconds != 300 {
                Text("\(step.timeoutSeconds)s")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
        .padding()
        .background(.quaternary.opacity(0.3))
        .cornerRadius(8)
    }
}

// MARK: - New Chain Sheet

struct NewChainSheet: View {
    let workflows: [WorkflowSidebarItem]
    let onCreate: (String, String, [ChainStep]) async -> Void
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var description = ""
    @State private var steps: [ChainStep] = []
    @State private var isCreating = false

    var body: some View {
        NavigationStack {
            Form {
                Section("Chain Details") {
                    TextField("Name", text: $name)
                    TextField("Description", text: $description, axis: .vertical)
                        .lineLimit(2...4)
                }

                Section("Steps") {
                    if steps.isEmpty {
                        Text("Add workflows to chain them together")
                            .foregroundStyle(.secondary)
                    } else {
                        ForEach(Array(steps.enumerated()), id: \.element.id) { index, step in
                            HStack {
                                Text("\(index + 1).")
                                    .foregroundStyle(.secondary)
                                Text(workflowName(for: step.workflowId))
                                Spacer()
                                Button {
                                    steps.remove(at: index)
                                } label: {
                                    Image(systemName: "minus.circle.fill")
                                        .foregroundStyle(.red)
                                }
                                .buttonStyle(.borderless)
                            }
                        }
                        .onMove { from, to in
                            steps.move(fromOffsets: from, toOffset: to)
                        }
                    }

                    Menu {
                        ForEach(workflows) { workflow in
                            Button(workflow.name) {
                                addStep(workflowId: workflow.id)
                            }
                        }
                    } label: {
                        Label("Add Workflow", systemImage: "plus")
                    }
                }
            }
            .navigationTitle("New Chain")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        isCreating = true
                        Task {
                            await onCreate(name, description, steps)
                            dismiss()
                        }
                    }
                    .disabled(name.isEmpty || steps.isEmpty || isCreating)
                }
            }
        }
        .frame(minWidth: 400, minHeight: 400)
    }

    private func workflowName(for id: String) -> String {
        workflows.first { $0.id == id }?.name ?? "Unknown"
    }

    private func addStep(workflowId: String) {
        let step = ChainStep(
            id: UUID().uuidString,
            workflowId: workflowId,
            name: "",
            inputMappings: [],
            staticInputs: [:],
            condition: nil,
            continueOnError: false,
            timeoutSeconds: 300
        )
        steps.append(step)
    }
}

#Preview {
    WorkflowChainListView(apiClient: APIClient())
}
