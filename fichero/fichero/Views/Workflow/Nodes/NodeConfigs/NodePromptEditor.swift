import SwiftUI

/// The ONLY code that reads or writes a node's `prompt` override.
/// Spec: docs/contributor/specs/workflow-node-config.md §B.
///
/// Pure so the rule "looking never writes, only an edit writes" is a unit
/// test, not a hope: the editor's appearance path calls nothing here.
enum NodePromptOverride {
    /// The saved override, or "" when the node runs on the tool default.
    static func current(in config: [String: AnyCodableValue]?) -> String {
        config?["prompt"]?.stringValue ?? ""
    }

    /// Writes `text` as the override; an empty edit REMOVES the key so the
    /// server default applies again (`nodeconfig.roundtrip.remove-means-absent`).
    /// Removing from an absent config leaves it absent — no write on "clear".
    static func apply(_ text: String, to config: inout [String: AnyCodableValue]?) {
        if text.isEmpty {
            config?.removeValue(forKey: "prompt")
        } else {
            if config == nil { config = [:] }
            config?["prompt"] = .string(text)
        }
    }

    /// The ghost placeholder: the prompt the run would send with no override.
    /// Prefers the server-assembled prompt for the current config, falls back
    /// to the registry default while the server has not answered yet
    /// (`nodeconfig.prompt.visible-before-registry`). An empty string from
    /// either source is NOT a prompt (the tool registers none) → nil, never a
    /// blank ghost.
    static func ghost(backend: String?, registry: String?) -> String? {
        if let backend, !backend.isEmpty { return backend }
        if let registry, !registry.isEmpty { return registry }
        return nil
    }
}

/// The one prompt editor every prompt-bearing node config composes
/// (`nodeconfig.prompt.one-editor-component`). Same shape as the schema-driven
/// `DynamicConfigView.promptEditor`: the default is a GHOST behind an empty
/// editor, typing writes an override, "Reset to default" removes it.
///
/// The text binding is derived from `node.config` — there is no `@State` copy
/// of the default to leak into config on appear, which is what used to pin a
/// stale default as a user override the moment a popover opened
/// (`nodeconfig.prompt.default-is-ghost-not-text`).
struct NodePromptEditor: View {
    @Binding var node: WorkflowNode
    /// Server-assembled prompt for the node's current inputs, when fetched.
    let backendPrompt: String?
    /// Registry default from the tool definition, when loaded.
    let registryPrompt: String?
    var title: String = "Prompt"

    private var override: String { NodePromptOverride.current(in: node.config) }
    private var ghost: String? {
        NodePromptOverride.ghost(backend: backendPrompt, registry: registryPrompt)
    }

    private var overrideBinding: Binding<String> {
        Binding(
            get: { NodePromptOverride.current(in: node.config) },
            set: { NodePromptOverride.apply($0, to: &node.config) }
        )
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.caption)
                .foregroundColor(.secondary)

            ZStack(alignment: .topLeading) {
                if override.isEmpty, let ghost {
                    Text(ghost)
                        .font(.caption)
                        .foregroundColor(.secondary.opacity(0.7))
                        .padding(.horizontal, 4)
                        .padding(.vertical, 8)
                        .accessibilityLabel("Default prompt: \(ghost)")
                }

                MacPlainTextEditor(text: overrideBinding, font: .preferredFont(forTextStyle: .caption1))
            }
            .frame(minHeight: 80)
            .background(Color(.textBackgroundColor))
            .overlay(
                RoundedRectangle(cornerRadius: 4)
                    .stroke(Color(.separatorColor), lineWidth: 1)
            )

            if !override.isEmpty {
                Button {
                    NodePromptOverride.apply("", to: &node.config)
                } label: {
                    Label("Reset to default", systemImage: "arrow.counterclockwise")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .foregroundColor(.accentColor)
            } else if ghost != nil {
                Text("Shown is the tool default for this configuration. Type to override it.")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            } else {
                Text("Loading the tool's default prompt…")
                    .font(.caption2)
                    .foregroundColor(.secondary)
            }
        }
    }
}
