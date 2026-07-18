import FicheroAPIClient
import SwiftUI

/// Batch surface tabs (#3536): create a new folder-fan-out batch, or review
/// existing batches. Shares the app's SurfaceTabBar chrome.
enum BatchSurfaceTab: String, CaseIterable, Identifiable, SurfaceTab {
    case newBatch
    case batches

    var id: String { rawValue }
    var title: String {
        switch self {
        case .newBatch: return "New Batch"
        case .batches: return "Batches"
        }
    }
    var icon: String {
        switch self {
        case .newBatch: return "square.stack.3d.up.badge.a"
        case .batches: return "square.stack.3d.up"
        }
    }
    var help: String {
        switch self {
        case .newBatch: return "New Batch — run a workflow across many folders separately"
        case .batches: return "Batches — existing batch runs and their progress"
        }
    }
}

/// Batch-mode GUI (#3536): run one workflow across dozens of folders SEPARATELY
/// — one batch item per folder (each scoped to that folder's documents), so
/// every folder is its own run tracked in Activity. Consumes the existing batch
/// backend via `BatchStore` (the endpoint accessor); reuses the SurfaceTabBar /
/// MiniToolbar chrome for consistency with the Workflow surface.
struct BatchRunView: View {
    @Environment(BatchStore.self) private var batchStore
    @Environment(WorkflowService.self) private var workflowService
    @Environment(DocumentStore.self) private var documentStore

    @State private var workflows: [WorkflowResponse] = []
    @State private var selectedWorkflowId: String?
    @State private var selectedFolderIds: Set<String> = []
    @State private var isRunning = false
    @State private var message: String?
    @SceneStorage("batch.surfaceTab") private var tabRaw = BatchSurfaceTab.newBatch.rawValue

    private var tab: BatchSurfaceTab { BatchSurfaceTab(rawValue: tabRaw) ?? .newBatch }
    private var tabBinding: Binding<BatchSurfaceTab> {
        Binding(get: { tab }, set: { tabRaw = $0.rawValue })
    }

    /// The current library level's folders — the fan-out targets.
    private var folders: [Document] {
        documentStore.currentDocuments.filter { $0.docType == .folder }
    }

    var body: some View {
        VStack(spacing: 0) {
            SurfaceTabBar(tabs: BatchSurfaceTab.allCases, selection: tabBinding, accessibilityID: "batchSurfaceTabBar")
            Divider()
            switch tab {
            case .newBatch: newBatchContent
            case .batches: batchesListContent
            }
            Divider()
            bottomBar
        }
        .task {
            await loadWorkflows()
            await batchStore.load()
        }
    }

    // MARK: - New batch

    @ViewBuilder
    private var newBatchContent: some View {
        Form {
            Section("Workflow") {
                Picker("Run", selection: $selectedWorkflowId) {
                    Text("Choose a workflow…").tag(String?.none)
                    ForEach(workflows, id: \.id) { workflow in
                        Text(workflow.name).tag(String?.some(workflow.id))
                    }
                }
            }
            Section("Folders — one separate run each") {
                if folders.isEmpty {
                    Text("No folders at this level. Open a library folder that contains sub-folders.")
                        .font(.caption).foregroundStyle(.secondary)
                } else {
                    ForEach(folders, id: \.id) { folder in
                        Toggle(isOn: folderBinding(folder.id)) {
                            Label(folder.name, systemImage: "folder")
                        }
                    }
                }
            }
        }
        .formStyle(.grouped)
    }

    private func folderBinding(_ id: String) -> Binding<Bool> {
        Binding(
            get: { selectedFolderIds.contains(id) },
            set: { isOn in
                if isOn { selectedFolderIds.insert(id) } else { selectedFolderIds.remove(id) }
            }
        )
    }

    // MARK: - Batches list

    @ViewBuilder
    private var batchesListContent: some View {
        if batchStore.batches.isEmpty {
            ContentUnavailableView(
                "No batches",
                systemImage: "square.stack.3d.up",
                description: Text("Run a workflow across folders from the New Batch tab.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else {
            List(batchStore.batches, id: \.batchId) { batch in
                HStack(spacing: 8) {
                    Image(systemName: "square.stack.3d.up")
                        .foregroundStyle(.secondary)
                    VStack(alignment: .leading, spacing: 1) {
                        Text(batch.workflowId).font(.body).lineLimit(1)
                        Text("\(batch.status) · \(batch.completedItems)/\(batch.totalItems)")
                            .font(.caption2).foregroundStyle(.secondary)
                    }
                    Spacer(minLength: 0)
                }
                .contextMenu {
                    Button(role: .destructive) {
                        Task { await batchStore.delete(batchId: batch.batchId) }
                    } label: {
                        Label("Delete Batch", systemImage: "trash")
                    }
                }
            }
            .listStyle(.inset)
        }
    }

    // MARK: - Bottom bar

    private var bottomBar: some View {
        MiniToolbar {
            Text(bottomStatus)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
            if tab == .newBatch {
                if isRunning { ProgressView().controlSize(.small) }
                Button {
                    runBatch()
                } label: {
                    Label("Run across \(selectedFolderIds.count) folder\(selectedFolderIds.count == 1 ? "" : "s")",
                          systemImage: "play.fill")
                }
                .buttonStyle(.borderedProminent)
                .controlSize(.small)
                .disabled(selectedWorkflowId == nil || selectedFolderIds.isEmpty || isRunning)
            }
        }
    }

    private var bottomStatus: String {
        if let message { return message }
        switch tab {
        case .newBatch:
            return "\(selectedFolderIds.count) folder\(selectedFolderIds.count == 1 ? "" : "s") selected"
        case .batches:
            let count = batchStore.batches.count
            return count == 0 ? "No batches" : "\(count) batch\(count == 1 ? "" : "es")"
        }
    }

    // MARK: - Actions

    private func loadWorkflows() async {
        do { workflows = try await workflowService.listWorkflows() } catch { workflows = [] }
    }

    /// Fan out one batch item per selected folder (each scoped to that folder's
    /// documents), then track it in Activity.
    private func runBatch() {
        guard let workflowId = selectedWorkflowId, !selectedFolderIds.isEmpty else { return }
        isRunning = true
        message = nil
        let folderIds = selectedFolderIds
        Task {
            var folderInputs: [(id: String, documentIds: [String])] = []
            for folderId in folderIds {
                let docIds = await documentStore.children(of: folderId).map(\.id)
                folderInputs.append((id: folderId, documentIds: docIds))
            }
            let batch = await batchStore.runFolderBatch(workflowId: workflowId, folders: folderInputs)
            isRunning = false
            if batch != nil {
                message = "Started \(folderInputs.count) folder run\(folderInputs.count == 1 ? "" : "s") — track them in Activity."
                selectedFolderIds.removeAll()
                tabRaw = BatchSurfaceTab.batches.rawValue
            } else {
                message = batchStore.lastError ?? "Couldn't start the batch."
            }
        }
    }
}
