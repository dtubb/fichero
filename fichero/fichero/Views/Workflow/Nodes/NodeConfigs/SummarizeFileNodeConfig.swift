import SwiftUI

/// Configuration view for summarize_file node
struct SummarizeFileNodeConfig: View {
    @Binding var node: WorkflowNode

    let toolInfo: ToolInfo?
    let backendPrompt: String?

    @State private var summaryStyle: String = "brief"
    @State private var maxLength: Int = 200

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            // Style
            VStack(alignment: .leading, spacing: 4) {
                Text("Style")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("Style", selection: $summaryStyle) {
                    Text("Brief").tag("brief")
                    Text("Detailed").tag("detailed")
                    Text("Bullets").tag("bullets")
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
                ), in: 50...1000, step: 50)
                .onChange(of: maxLength) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["max_length"] = .int(newValue)
                }
            }

            // Thinking mode
            ThinkingModePicker(node: $node)

            // Prompt: the style/length-aware default shows as a ghost so the
            // user sees what they would override (`nodeconfig.fields.summarize-file.prompt`).
            NodePromptEditor(
                node: $node,
                backendPrompt: backendPrompt,
                registryPrompt: toolInfo?.defaultPrompt
            )
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
    }
}
