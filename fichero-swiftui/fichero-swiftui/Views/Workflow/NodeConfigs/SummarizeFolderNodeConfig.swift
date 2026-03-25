import SwiftUI

/// Configuration view for summarize_folder node
struct SummarizeFolderNodeConfig: View {
    @Binding var node: WorkflowNode

    @State private var summaryStyle: String = "brief"
    @State private var maxLength: Int = 200
    @State private var includeThemes: Bool = true

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
                ), in: 100...2000, step: 100)
                .onChange(of: maxLength) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["max_length"] = .int(newValue)
                }
            }

            // Thinking mode
            ThinkingModePicker(node: $node)

            // Include themes
            Toggle("Include Themes", isOn: $includeThemes)
                .font(.caption)
                .onChange(of: includeThemes) { _, newValue in
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["include_themes"] = .bool(newValue)
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

        if let configValue = node.config?["include_themes"],
           case .bool(let themes) = configValue {
            includeThemes = themes
        }
    }
}
