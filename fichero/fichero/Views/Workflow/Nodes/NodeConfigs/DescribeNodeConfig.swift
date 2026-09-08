import SwiftUI

/// Configuration view for describe node
struct DescribeNodeConfig: View {
    @Binding var node: WorkflowNode

    let toolInfo: ToolInfo?
    let backendPrompt: String?

    @State private var detailLevel: String = "detailed"
    @State private var focusText: String = ""

    var body: some View {
        // Describe tool ONLY supports LLM vision (no Apple Vision)
        // The backend hardcodes vision_mode="llm" since it requires semantic understanding
        VStack(alignment: .leading, spacing: 12) {
            // Detail level
            VStack(alignment: .leading, spacing: 4) {
                Text("Detail Level")
                    .font(.caption)
                    .foregroundColor(.secondary)

                Picker("", selection: $detailLevel) {
                    Text("Brief").tag("brief")
                    Text("Detailed").tag("detailed")
                    Text("Comprehensive").tag("comprehensive")
                }
                .labelsHidden()
                .pickerStyle(.segmented)
                .onChange(of: detailLevel) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["detail_level"] = .string(newValue)
                }
            }

            // Focus
            VStack(alignment: .leading, spacing: 4) {
                Text("Focus (optional)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                TextField("e.g., people, objects, text, scene", text: $focusText)
                    .textFieldStyle(.roundedBorder)
                    .onChange(of: focusText) { _, newValue in
                        if newValue.isEmpty {
                            node.config?.removeValue(forKey: "focus")
                        } else {
                            if node.config == nil {
                                node.config = [:]
                            }
                            node.config?["focus"] = .string(newValue)
                        }
                    }
            }

            // Thinking mode
            ThinkingModePicker(node: $node)

            // Prompt: ghost default (for the current detail/focus), override on
            // edit — the one shared editor; nothing here writes config on appear.
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
        if let configValue = node.config?["detail_level"],
           case .string(let level) = configValue {
            detailLevel = level
        }

        if let configValue = node.config?["focus"],
           case .string(let focus) = configValue {
            focusText = focus
        }
    }
}
