import SwiftUI

/// Configuration view for summarize_collection node
struct SummarizeCollectionNodeConfig: View {
    @Binding var node: WorkflowNode

    @State private var summaryStyle: String = "executive"
    @State private var maxLength: Int = 500
    @State private var includeStatistics: Bool = true

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Style
            VStack(alignment: .leading, spacing: 4) {
                Text("Style")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Style", selection: $summaryStyle) {
                    Text("Executive").tag("executive")
                    Text("Detailed").tag("detailed")
                    Text("Narrative").tag("narrative")
                }
                .pickerStyle(.segmented)
                .onChange(of: summaryStyle) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["style"] = .string(newValue)
                }
            }

            // Max length
            VStack(alignment: .leading, spacing: 4) {
                Text("Max Words: \(maxLength)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Slider(value: Binding(
                    get: { Double(maxLength) },
                    set: { maxLength = Int($0) }
                ), in: 200...3000, step: 100)
                .onChange(of: maxLength) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["max_length"] = .int(newValue)
                }
            }

            // Thinking mode
            ThinkingModePicker(node: $node)

            // Include statistics
            Toggle("Include Statistics", isOn: $includeStatistics)
                .font(.caption)
                .onChange(of: includeStatistics) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["include_statistics"] = .bool(newValue)
                }
        }
        .onAppear {
            loadInitialState()
        }
    }

    private func loadInitialState() {
        if let configValue = node.config?["style"],
           case .string(let style) = configValue {
            summaryStyle = style
        }

        if let configValue = node.config?["max_length"],
           case .int(let length) = configValue {
            maxLength = length
        }

        if let configValue = node.config?["include_statistics"],
           case .bool(let stats) = configValue {
            includeStatistics = stats
        }
    }
}
