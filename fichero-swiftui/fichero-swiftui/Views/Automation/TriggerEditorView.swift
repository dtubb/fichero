import SwiftUI
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "TriggerEditorView")

/// Full-page editor for creating and editing file watch triggers
/// Similar to workflow canvas - used instead of dialog sheets
// swiftlint:disable:next type_body_length
struct TriggerEditorView: View {
    @EnvironmentObject var apiClient: APIClient
    @EnvironmentObject var workflowStore: WorkflowStore

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
        HSplitView {
            // Left panel - Form
            formPanel
                .frame(minWidth: 350, idealWidth: 400, maxWidth: 500)

            // Right panel - Preview/Help
            previewPanel
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

    // MARK: - Form Panel

    @ViewBuilder
    private var formPanel: some View {
        Form {
            // Basic Information
            Section("Basic Information") {
                TextField("Name", text: $name)
                    .textFieldStyle(.roundedBorder)

                Picker("Workflow", selection: $selectedWorkflowId) {
                    Text("Select workflow...").tag("")
                    ForEach(workflowStore.workflows) { workflow in
                        Text(workflow.name).tag(workflow.id)
                    }
                }
            }

            // Watch Path
            Section("Watch Location") {
                HStack {
                    TextField("Watch Path", text: $watchPath)
                        .textFieldStyle(.roundedBorder)

                    Button {
                        showFolderPicker = true
                    } label: {
                        Image(systemName: "folder")
                    }
                }

                Toggle("Include subfolders", isOn: $recursive)
            }

            // Events to Watch
            Section("Events") {
                Toggle("Created", isOn: $eventCreated)
                Toggle("Modified", isOn: $eventModified)
                Toggle("Deleted", isOn: $eventDeleted)
                Toggle("Moved", isOn: $eventMoved)
            }

            // File Filters
            Section("File Filters") {
                Picker("Filter Mode", selection: $filterMode) {
                    Text("Glob Pattern").tag("glob")
                    Text("Regex").tag("regex")
                    Text("Extensions").tag("extension")
                }
                .pickerStyle(.segmented)

                filterModeFields
            }

            // Advanced Options
            DisclosureGroup("Advanced Options", isExpanded: $showAdvanced) {
                advancedOptions
            }

            // Error display
            if let error = error {
                Section {
                    HStack {
                        Image(systemName: "exclamationmark.triangle.fill")
                            .foregroundStyle(.orange)
                        Text(error)
                            .foregroundStyle(.red)
                    }
                }
            }
        }
        .formStyle(.grouped)
    }

    @ViewBuilder
    private var filterModeFields: some View {
        switch filterMode {
        case "glob":
            VStack(alignment: .leading, spacing: 8) {
                TextField("Pattern", text: $filterPattern)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(.body, design: .monospaced))

                Text("Examples: *.jpg, *.{jpg,png}, **/*.pdf")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

        case "regex":
            VStack(alignment: .leading, spacing: 8) {
                TextField("Pattern", text: $filterPattern)
                    .textFieldStyle(.roundedBorder)
                    .font(.system(.body, design: .monospaced))

                Text("Examples: .*\\.jpg$, \\d{4}-\\d{2}-\\d{2}\\.txt")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

        case "extension":
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    TextField("Add extension", text: $extensionInput)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit {
                            addExtension()
                        }

                    Button("Add") {
                        addExtension()
                    }
                    .disabled(extensionInput.isEmpty)
                }

                if !filterExtensions.isEmpty {
                    FlowLayout(spacing: 4) {
                        ForEach(filterExtensions, id: \.self) { ext in
                            extensionTag(ext)
                        }
                    }
                }

                Text("Enter extensions without dot (e.g., jpg, png, pdf)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

        default:
            EmptyView()
        }
    }

    @ViewBuilder
    private func extensionTag(_ ext: String) -> some View {
        HStack(spacing: 4) {
            Text(".\(ext)")
                .font(.caption)

            Button {
                filterExtensions.removeAll { $0 == ext }
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.caption)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color.accentColor.opacity(0.2))
        .cornerRadius(4)
    }

    @ViewBuilder
    private var advancedOptions: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Exclude patterns
            VStack(alignment: .leading, spacing: 4) {
                Text("Exclude Patterns")
                    .font(.subheadline)

                HStack {
                    TextField("Add pattern", text: $excludeInput)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit {
                            addExcludePattern()
                        }

                    Button("Add") {
                        addExcludePattern()
                    }
                    .disabled(excludeInput.isEmpty)
                }

                if !excludePatterns.isEmpty {
                    FlowLayout(spacing: 4) {
                        ForEach(excludePatterns, id: \.self) { pattern in
                            excludeTag(pattern)
                        }
                    }
                }

                Text("Patterns like .DS_Store, *.tmp, node_modules/**")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Divider()

            // Debounce
            VStack(alignment: .leading, spacing: 4) {
                Text("Debounce: \(debounceSeconds, specifier: "%.1f")s")
                    .font(.subheadline)

                Slider(value: $debounceSeconds, in: 0...10, step: 0.5)

                Text("Delay before triggering to avoid rapid-fire events")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            // Batch delay
            VStack(alignment: .leading, spacing: 4) {
                Text("Batch Delay: \(batchDelaySeconds, specifier: "%.1f")s")
                    .font(.subheadline)

                Slider(value: $batchDelaySeconds, in: 0...30, step: 1)

                Text("Wait to collect multiple files into one batch")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Divider()

            // Batch settings
            Toggle("Batch Mode", isOn: $useBatch)

            if useBatch {
                Stepper("Max \(maxConcurrent) concurrent", value: $maxConcurrent, in: 1...100)
                    .padding(.leading)
            }
        }
    }

    @ViewBuilder
    private func excludeTag(_ pattern: String) -> some View {
        HStack(spacing: 4) {
            Text(pattern)
                .font(.caption)
                .foregroundStyle(.secondary)

            Button {
                excludePatterns.removeAll { $0 == pattern }
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .font(.caption)
            }
            .buttonStyle(.plain)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 4)
        .background(Color.secondary.opacity(0.2))
        .cornerRadius(4)
    }

    // MARK: - Preview Panel

    @ViewBuilder
    private var previewPanel: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                // Trigger Preview
                VStack(alignment: .leading, spacing: 12) {
                    Text("Trigger Preview")
                        .font(.headline)

                    if !name.isEmpty {
                        previewField("Name", name)
                    }

                    if let workflow = workflowStore.workflows.first(where: { $0.id == selectedWorkflowId }) {
                        previewField("Workflow", workflow.name)
                    }

                    if !watchPath.isEmpty {
                        previewField("Watch Path", watchPath)
                        previewField("Recursive", recursive ? "Yes" : "No")
                    }

                    previewField("Events", selectedEvents.joined(separator: ", "))

                    switch filterMode {
                    case "glob", "regex":
                        previewField("Filter Mode", filterMode.capitalized)
                        previewField("Pattern", filterPattern)
                    case "extension":
                        previewField("Extensions", filterExtensions.isEmpty ? "All" : filterExtensions.joined(separator: ", "))
                    default:
                        EmptyView()
                    }

                    if !excludePatterns.isEmpty {
                        previewField("Excludes", excludePatterns.joined(separator: ", "))
                    }

                    previewField("Debounce", String(format: "%.1fs", debounceSeconds))

                    if useBatch {
                        previewField("Batch Mode", "Enabled (max \(maxConcurrent) concurrent)")
                        previewField("Batch Delay", String(format: "%.1fs", batchDelaySeconds))
                    }
                }

                Divider()

                // Help section
                helpSection
            }
            .padding()
        }
        .background(Color(nsColor: .controlBackgroundColor))
    }

    @ViewBuilder
    private func previewField(_ label: String, _ value: String) -> some View {
        HStack(alignment: .top) {
            Text(label)
                .font(.caption)
                .foregroundStyle(.secondary)
                .frame(width: 80, alignment: .trailing)

            Text(value)
                .font(.body)
        }
    }

    @ViewBuilder
    private var helpSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("File Trigger Help")
                .font(.headline)

            VStack(alignment: .leading, spacing: 8) {
                Text("Events")
                    .font(.subheadline)
                    .fontWeight(.medium)

                VStack(alignment: .leading, spacing: 4) {
                    Text("• Created - New files added")
                    Text("• Modified - Files changed")
                    Text("• Deleted - Files removed")
                    Text("• Moved - Files renamed/moved")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 8) {
                Text("Filter Modes")
                    .font(.subheadline)
                    .fontWeight(.medium)

                VStack(alignment: .leading, spacing: 4) {
                    Text("• Glob - Shell-style patterns (*.jpg)")
                    Text("• Regex - Regular expressions (.*\\.jpg$)")
                    Text("• Extension - Match by file extension")
                }
                .font(.caption)
                .foregroundStyle(.secondary)
            }
        }
    }

    // MARK: - Helpers

    private func addExtension() {
        let ext = extensionInput.trimmingCharacters(in: .whitespacesAndNewlines)
            .trimmingCharacters(in: CharacterSet(charactersIn: "."))
        guard !ext.isEmpty, !filterExtensions.contains(ext) else { return }
        filterExtensions.append(ext)
        extensionInput = ""
    }

    private func addExcludePattern() {
        let pattern = excludeInput.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !pattern.isEmpty, !excludePatterns.contains(pattern) else { return }
        excludePatterns.append(pattern)
        excludeInput = ""
    }

    private func handleFolderSelection(_ result: Result<[URL], Error>) {
        switch result {
        case .success(let urls):
            if let url = urls.first {
                watchPath = url.path
            }
        case .failure(let error):
            logger.error("Failed to select folder: \(error.localizedDescription)")
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

// MARK: - Flow Layout for Tags

/// Simple flow layout for tags
struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let result = FlowResult(in: proposal.width ?? 0, subviews: subviews, spacing: spacing)
        return result.size
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        let result = FlowResult(in: bounds.width, subviews: subviews, spacing: spacing)
        for (index, subview) in subviews.enumerated() {
            subview.place(at: CGPoint(x: bounds.minX + result.positions[index].x,
                                      y: bounds.minY + result.positions[index].y),
                         proposal: .unspecified)
        }
    }

    struct FlowResult {
        var size: CGSize = .zero
        var positions: [CGPoint] = []

        init(in maxWidth: CGFloat, subviews: Subviews, spacing: CGFloat) {
            var currentX: CGFloat = 0
            var currentY: CGFloat = 0
            var lineHeight: CGFloat = 0

            for subview in subviews {
                let size = subview.sizeThatFits(.unspecified)

                if currentX + size.width > maxWidth && currentX > 0 {
                    currentX = 0
                    currentY += lineHeight + spacing
                    lineHeight = 0
                }

                positions.append(CGPoint(x: currentX, y: currentY))
                lineHeight = max(lineHeight, size.height)
                currentX += size.width + spacing
            }

            self.size = CGSize(width: maxWidth, height: currentY + lineHeight)
        }
    }
}

// Preview requires app context (APIClient, WorkflowStore)
