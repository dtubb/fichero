import SwiftUI

/// Left-panel form for TriggerEditorView
struct TriggerEditorFormPanel: View {
    @Environment(WorkflowStore.self) var workflowStore

    // Basic info
    @Binding var name: String
    @Binding var selectedWorkflowId: String

    // Watch location
    @Binding var watchPath: String
    @Binding var recursive: Bool
    @Binding var showFolderPicker: Bool

    // Events
    @Binding var eventCreated: Bool
    @Binding var eventModified: Bool
    @Binding var eventDeleted: Bool
    @Binding var eventMoved: Bool

    // Filter
    @Binding var filterMode: String
    @Binding var filterPattern: String
    @Binding var filterExtensions: [String]
    @Binding var extensionInput: String

    // Exclude patterns
    @Binding var excludePatterns: [String]
    @Binding var excludeInput: String

    // Advanced
    @Binding var showAdvanced: Bool
    @Binding var debounceSeconds: Double
    @Binding var batchDelaySeconds: Double
    @Binding var useBatch: Bool
    @Binding var maxConcurrent: Int

    // Error
    var error: String?

    var body: some View {
        Form {
            Section("Basic Information") {
                TextField("Name", text: $name)
                    .textFieldStyle(.roundedBorder)

                Picker("Workflow", selection: $selectedWorkflowId) {
                    Text("Select workflow...").tag("")
                    ForEach(workflowStore.directlyRunnableWorkflows) { workflow in
                        Text(workflow.name).tag(workflow.id)
                    }
                }
            }

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

            Section("Events") {
                Toggle("Created", isOn: $eventCreated)
                Toggle("Modified", isOn: $eventModified)
                Toggle("Deleted", isOn: $eventDeleted)
                Toggle("Moved", isOn: $eventMoved)
            }

            Section("File Filters") {
                Picker("Filter Mode", selection: $filterMode) {
                    Text("Glob Pattern").tag("glob")
                    Text("Regex").tag("regex")
                    Text("Extensions").tag("extension")
                }
                .pickerStyle(.segmented)

                filterModeFields
            }

            DisclosureGroup("Advanced Options", isExpanded: $showAdvanced) {
                advancedOptions
            }

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

    // MARK: - Filter Mode Fields

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
                        .onSubmit { addExtension() }

                    Button("Add") { addExtension() }
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

    // MARK: - Advanced Options

    @ViewBuilder
    private var advancedOptions: some View {
        VStack(alignment: .leading, spacing: 12) {
            VStack(alignment: .leading, spacing: 4) {
                Text("Exclude Patterns")
                    .font(.subheadline)

                HStack {
                    TextField("Add pattern", text: $excludeInput)
                        .textFieldStyle(.roundedBorder)
                        .onSubmit { addExcludePattern() }

                    Button("Add") { addExcludePattern() }
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

            VStack(alignment: .leading, spacing: 4) {
                Text("Debounce: \(debounceSeconds, specifier: "%.1f")s")
                    .font(.subheadline)

                Slider(value: $debounceSeconds, in: 0...10, step: 0.5)

                Text("Delay before triggering to avoid rapid-fire events")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            VStack(alignment: .leading, spacing: 4) {
                Text("Batch Delay: \(batchDelaySeconds, specifier: "%.1f")s")
                    .font(.subheadline)

                Slider(value: $batchDelaySeconds, in: 0...30, step: 1)

                Text("Wait to collect multiple files into one batch")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }

            Divider()

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
}
