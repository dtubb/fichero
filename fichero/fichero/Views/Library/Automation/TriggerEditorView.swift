import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "TriggerEditorView")

/// Full-page editor for creating and editing file watch triggers
/// Similar to workflow canvas - used instead of dialog sheets
struct TriggerEditorView: View {
    @Environment(APIClient.self) var apiClient
    @Environment(WorkflowStore.self) var workflowStore

    /// Existing trigger to edit, or nil for new trigger creation
    let existingTrigger: TriggerInfo?

    /// Callback when trigger is saved
    var onSave: ((TriggerInfo) -> Void)?

    // Form state
    @State private var name = ""
    @State private var selectedWorkflowId = ""
    @State private var watchPath = ""
    @State private var recursive = true
    @State private var eventCreated = true
    @State private var eventModified = true
    @State private var eventDeleted = false
    @State private var eventMoved = false
    @State private var filterMode = "glob"
    @State private var filterPattern = "*.*"
    @State private var filterExtensions: [String] = []
    @State private var extensionInput = ""
    @State private var excludePatterns: [String] = []
    @State private var excludeInput = ""
    @State private var debounceSeconds: Double = 1.0
    @State private var batchDelaySeconds: Double = 5.0
    @State private var useBatch = false
    @State private var maxConcurrent = 1

    // UI state
    @State private var isSaving = false
    @State private var error: String?
    @State private var showAdvanced = false
    @State private var showFolderPicker = false

    private var isEditing: Bool { existingTrigger != nil }
    private var isValid: Bool { !name.isEmpty && !selectedWorkflowId.isEmpty && !watchPath.isEmpty }

    private var selectedEvents: [String] {
        var events: [String] = []
        if eventCreated { events.append("created") }
        if eventModified { events.append("modified") }
        if eventDeleted { events.append("deleted") }
        if eventMoved { events.append("moved") }
        return events.isEmpty ? ["any"] : events
    }

    var body: some View {
        PlatformHSplitView {
            TriggerEditorFormPanel(
                name: $name,
                selectedWorkflowId: $selectedWorkflowId,
                watchPath: $watchPath,
                recursive: $recursive,
                showFolderPicker: $showFolderPicker,
                eventCreated: $eventCreated,
                eventModified: $eventModified,
                eventDeleted: $eventDeleted,
                eventMoved: $eventMoved,
                filterMode: $filterMode,
                filterPattern: $filterPattern,
                filterExtensions: $filterExtensions,
                extensionInput: $extensionInput,
                excludePatterns: $excludePatterns,
                excludeInput: $excludeInput,
                showAdvanced: $showAdvanced,
                debounceSeconds: $debounceSeconds,
                batchDelaySeconds: $batchDelaySeconds,
                useBatch: $useBatch,
                maxConcurrent: $maxConcurrent,
                error: error
            )
            .frame(minWidth: 350, idealWidth: 400, maxWidth: 500)

            TriggerEditorPreviewPanel(
                name: name,
                selectedWorkflowId: selectedWorkflowId,
                watchPath: watchPath,
                recursive: recursive,
                selectedEvents: selectedEvents,
                filterMode: filterMode,
                filterPattern: filterPattern,
                filterExtensions: filterExtensions,
                excludePatterns: excludePatterns,
                debounceSeconds: debounceSeconds,
                useBatch: useBatch,
                maxConcurrent: maxConcurrent,
                batchDelaySeconds: batchDelaySeconds
            )
            .frame(minWidth: 300, idealWidth: 350)
        }
        .navigationTitle(isEditing ? "Edit Trigger" : "New Trigger")
        .toolbar {
            ToolbarItem(placement: .primaryAction) {
                Button {
                    Task { await saveTrigger() }
                } label: {
                    if isSaving {
                        ProgressView()
                            .scaleEffect(0.8)
                    } else {
                        Label("Save", systemImage: "checkmark.circle")
                    }
                }
                .disabled(!isValid || isSaving)
            }
        }
        .onAppear {
            populateFromExisting()
        }
        .fileImporter(
            isPresented: $showFolderPicker,
            allowedContentTypes: [.folder],
            allowsMultipleSelection: false
        ) { result in
            handleFolderSelection(result)
        }
    }

    // MARK: - Helpers

    private func handleFolderSelection(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            if let url = urls.first {
                watchPath = url.path
            }
        case .failure(let err):
            logger.error("Failed to select folder: \(err.localizedDescription)")
            self.error = "Failed to select folder"
        }
    }

    private func populateFromExisting() {
        guard let trigger = existingTrigger else { return }

        name = trigger.name
        selectedWorkflowId = trigger.workflowId
        watchPath = trigger.watchPath
        recursive = trigger.recursive
        filterMode = trigger.filterMode
        filterPattern = trigger.filterPattern ?? "*.*"
        filterExtensions = trigger.filterExtensions
        excludePatterns = trigger.excludePatterns
        debounceSeconds = trigger.debounceSeconds
        batchDelaySeconds = trigger.batchDelaySeconds
        useBatch = trigger.useBatch
        maxConcurrent = trigger.maxConcurrent

        // Parse events
        eventCreated = trigger.events.contains("created") || trigger.events.contains("any")
        eventModified = trigger.events.contains("modified") || trigger.events.contains("any")
        eventDeleted = trigger.events.contains("deleted") || trigger.events.contains("any")
        eventMoved = trigger.events.contains("moved") || trigger.events.contains("any")
    }

    // MARK: - Actions

    private func saveTrigger() async {
        guard isValid else { return }
        isSaving = true
        error = nil

        do {
            let config = TriggerConfigRequest(
                watchPath: watchPath,
                recursive: recursive,
                events: selectedEvents,
                filterMode: filterMode,
                filterPattern: filterMode == "extension" ? nil : filterPattern,
                filterExtensions: filterExtensions,
                excludePatterns: excludePatterns,
                debounceSeconds: debounceSeconds,
                batchDelaySeconds: batchDelaySeconds
            )

            let request = CreateTriggerRequest(
                name: name,
                workflowId: selectedWorkflowId,
                config: config,
                inputsTemplate: [:],
                useBatch: useBatch,
                maxConcurrent: maxConcurrent
            )

            let service = AutomationService(apiClient: apiClient)
            let savedTrigger = try await service.createTrigger(request: request)

            logger.info("Saved trigger: \(name)")

            // Callback for parent to refresh (SidebarView manages data via Combine)
            onSave?(savedTrigger)

        } catch {
            logger.error("Failed to save trigger: \(error.localizedDescription)")
            self.error = error.localizedDescription
        }

        isSaving = false
    }
}

// MARK: - Preview

#Preview {
    let libraryManager = LibraryManager.shared
    let library = libraryManager.globalLibrary!

    TriggerEditorView(existingTrigger: nil)
        .environment(library.automationService)
        .environment(library.workflowStore)
        .frame(width: 700, height: 600)
}
