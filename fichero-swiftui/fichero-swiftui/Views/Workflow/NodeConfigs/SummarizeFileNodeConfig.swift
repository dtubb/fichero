import SwiftUI

/// Configuration view for summarize_file node
struct SummarizeFileNodeConfig: View {
    @Binding var node: WorkflowNode

    @State private var summaryStyle: String = "brief"
    @State private var maxLength: Int = 200
    @State private var promptText: String = ""

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

            // Custom prompt
            VStack(alignment: .leading, spacing: 4) {
                Text("Custom Prompt (optional)")
                    .font(.caption)
                    .foregroundColor(.secondary)

                MacPlainTextEditor(text: $promptText, font: .preferredFont(forTextStyle: .caption1))
                    .frame(minHeight: 60)
                    .overlay(
                        RoundedRectangle(cornerRadius: 4)
                            .stroke(Color(.separatorColor), lineWidth: 1)
                    )
                    .onChange(of: promptText) { _, newValue in
                        if newValue.isEmpty {
                            node.config?.removeValue(forKey: "prompt")
                        } else {
                            if node.config == nil {
                                node.config = [:]
                            }
                            node.config?["prompt"] = .string(newValue)
                        }
                    }
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

        if let configValue = node.config?["prompt"],
           case .string(let prompt) = configValue {
            promptText = prompt
        }
    }
}
