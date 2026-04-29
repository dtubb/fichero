import SwiftUI

/// Reusable thinking mode picker for LLM-based workflow node configs.
/// Maps to the backend's `thinking_mode` config key (off/short/medium/long).
struct ThinkingModePicker: View {
    @Binding var node: WorkflowNode

    @State private var thinkingMode: String = "off"

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Thinking Mode")
                .font(.caption)
                .foregroundColor(.secondary)

            Picker("", selection: $thinkingMode) {
                Text("Off").tag("off")
                Text("Short").tag("short")
                Text("Medium").tag("medium")
                Text("Long").tag("long")
            }
            .labelsHidden()
            .pickerStyle(.segmented)
            .onChange(of: thinkingMode) { _, newValue in
                if newValue == "off" {
                    node.config?.removeValue(forKey: "thinking_mode")
                } else {
                    if node.config == nil {
                        node.config = [:]
                    }
                    node.config?["thinking_mode"] = .string(newValue)
                }
            }

            Text("Extended thinking for complex reasoning tasks")
                .font(.caption2)
                .foregroundColor(.secondary)
        }
        .onAppear {
            if let configValue = node.config?["thinking_mode"],
               case .string(let mode) = configValue {
                thinkingMode = mode
            }
        }
    }
}
