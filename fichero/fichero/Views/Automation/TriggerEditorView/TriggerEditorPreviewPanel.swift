import SwiftUI

/// Right-panel preview and help for TriggerEditorView
struct TriggerEditorPreviewPanel: View {
    @Environment(WorkflowStore.self) var workflowStore

    let name: String
    let selectedWorkflowId: String
    let watchPath: String
    let recursive: Bool
    let selectedEvents: [String]
    let filterMode: String
    let filterPattern: String
    let filterExtensions: [String]
    let excludePatterns: [String]
    let debounceSeconds: Double
    let useBatch: Bool
    let maxConcurrent: Int
    let batchDelaySeconds: Double

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 20) {
                triggerPreview
                Divider()
                helpSection
            }
            .padding()
        }
        .background(Color(platformColor: .controlBackgroundColor))
    }

    // MARK: - Trigger Preview

    @ViewBuilder
    private var triggerPreview: some View {
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
                let extensionText = filterExtensions.isEmpty ? "All" : filterExtensions.joined(separator: ", ")
                previewField("Extensions", extensionText)
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

    // MARK: - Help Section

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
}
