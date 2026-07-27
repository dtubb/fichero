import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "TriggerCreationSheet")

/// Sheet for creating a new file trigger
struct TriggerCreationSheet: View {
    @Environment(APIClient.self) var apiClient
    @Environment(WorkflowStore.self) var workflowStore
    @Environment(\.dismiss) private var dismiss

    @State private var name = ""
    @State private var selectedWorkflowId = ""
    @State private var watchPath = ""
    @State private var recursive = true
    @State private var selectedEvents: Set<String> = ["created"]
    @State private var filterMode = "extension"
    @State private var filterPattern = ""
    @State private var filterExtensions = "pdf,jpg,png"
    @State private var debounceSeconds: Double = 1.0
    @State private var isCreating = false
    @State private var errorMessage: String?

    let onCreate: () -> Void

    private let availableEvents = ["created", "modified", "deleted", "moved"]

    var body: some View {
        NavigationStack {
            Form {
                Section("Basic Information") {
                    TextField("Name", text: $name)

                    Picker("Workflow", selection: $selectedWorkflowId) {
                        Text("Select workflow...").tag("")
                        ForEach(workflowStore.directlyRunnableWorkflows) { workflow in
                            Text(workflow.name).tag(workflow.id)
                        }
                    }
                }

                Section("Watch Location") {
                    HStack {
                        TextField("Folder Path", text: $watchPath)
                        Button("Browse...") {
                            selectFolder()
                        }
                    }

                    Toggle("Include subfolders", isOn: $recursive)
                }

                Section("File Events") {
                    ForEach(availableEvents, id: \.self) { event in
                        Toggle(event.capitalized, isOn: Binding(
                            get: { selectedEvents.contains(event) },
                            set: { isOn in
                                if isOn {
                                    selectedEvents.insert(event)
                                } else {
                                    selectedEvents.remove(event)
                                }
                            }
                        ))
                    }
                }

                Section("File Filter") {
                    Picker("Filter Mode", selection: $filterMode) {
                        Text("By Extension").tag("extension")
                        Text("Glob Pattern").tag("glob")
                        Text("Regex").tag("regex")
                    }

                    if filterMode == "extension" {
                        TextField("Extensions (comma-separated)", text: $filterExtensions)
                        Text("e.g., 'pdf,jpg,png'")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else {
                        TextField("Pattern", text: $filterPattern)
                        if filterMode == "glob" {
                            Text("e.g., '*.pdf' or 'report_*.xlsx'")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        } else {
                            Text("e.g., '.*\\.pdf$'")
                                .font(.caption)
                                .foregroundStyle(.secondary)
                        }
                    }
                }

                Section("Advanced") {
                    Stepper("Debounce: \(String(format: "%.1f", debounceSeconds))s",
                            value: $debounceSeconds, in: 0.1...10.0, step: 0.5)
                    Text("Wait time after file change before triggering")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                if let error = errorMessage {
                    Section {
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
            .navigationTitle("New Trigger")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }

                ToolbarItem(placement: .confirmationAction) {
                    Button("Create") {
                        createTrigger()
                    }
                    .disabled(name.isEmpty || selectedWorkflowId.isEmpty || watchPath.isEmpty || isCreating)
                }
            }
        }
        .frame(minWidth: 450, minHeight: 500)
    }

    private func selectFolder() {
        #if os(macOS)
        let panel = NSOpenPanel()
        panel.canChooseFiles = false
        panel.canChooseDirectories = true
        panel.allowsMultipleSelection = false
        panel.message = "Select folder to watch"

        if panel.runModal() == .OK, let url = panel.url {
            watchPath = url.path
        }
        #else
        // iOS: folder picker goes through UIDocumentPickerViewController in
        // the iPad UI pass. Until then, the field stays empty.
        _ = watchPath
        #endif
    }

    private func createTrigger() {
        guard !isCreating else { return }
        isCreating = true
        errorMessage = nil

        Task {
            do {
                let extensions = filterMode == "extension"
                    ? filterExtensions.split(separator: ",").map { String($0.trimmingCharacters(in: .whitespaces)) }
                    : []

                let config = TriggerConfigRequest(
                    watchPath: watchPath,
                    recursive: recursive,
                    events: Array(selectedEvents),
                    filterMode: filterMode,
                    filterPattern: filterMode != "extension" ? filterPattern : nil,
                    filterExtensions: extensions,
                    excludePatterns: [],
                    debounceSeconds: debounceSeconds,
                    batchDelaySeconds: 0.5
                )

                let request = CreateTriggerRequest(
                    name: name,
                    workflowId: selectedWorkflowId,
                    config: config,
                    inputsTemplate: [:],
                    useBatch: false,
                    maxConcurrent: 1
                )

                let automationService = AutomationService(apiClient: apiClient)
                _ = try await automationService.createTrigger(request: request)

                logger.info("Created trigger: \(name)")
                onCreate()
                dismiss()
            } catch {
                logger.error("Failed to create trigger: \(error.localizedDescription)")
                errorMessage = error.localizedDescription
            }
            isCreating = false
        }
    }
}
