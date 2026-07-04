import SwiftUI

/// Toolbar for Chat view with model selection and chat controls
struct ChatViewToolbar: View {
    // Document scope
    let selectedDocumentsCount: Int
    let onClearDocuments: () -> Void

    // Model selection
    let providers: [LLMProvider]
    @Binding var selectedProvider: String
    @Binding var selectedModel: String

    // Actions
    let onNewChat: () -> Void

    var body: some View {
        // Rebuilt on MiniToolbar (#3038) — standard height + glass chrome, one
        // shared toolbar language. Controls/actions unchanged; MiniToolbar
        // supplies the row layout, padding, and material the old plain HStack +
        // .ultraThinMaterial did by hand.
        MiniToolbar(content: {
            // Document scope indicator (left side)
            if selectedDocumentsCount == 0 {
                Label("All documents", systemImage: "doc.on.doc")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            } else {
                Label("\(selectedDocumentsCount) documents", systemImage: "checkmark.circle.fill")
                    .font(.caption)
                    .foregroundStyle(.green)

                Button("Clear") {
                    onClearDocuments()
                }
                .font(.caption)
                .buttonStyle(.plain)
                .foregroundColor(.accentColor)
            }

            Spacer()

            // Model picker and controls (right side)
            modelPicker

            // New Chat button
            Button(action: onNewChat) {
                Label("New Chat", systemImage: "plus.bubble")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        })
    }

    private var modelPicker: some View {
        Menu {
            ForEach(providers) { provider in
                if provider.available {
                    Section(provider.name) {
                        ForEach(provider.models, id: \.self) { model in
                            Button {
                                selectedProvider = provider.id
                                selectedModel = model
                            } label: {
                                HStack {
                                    Text(model)
                                    if selectedProvider == provider.id && selectedModel == model {
                                        Image(systemName: "checkmark")
                                    }
                                }
                            }
                        }
                    }
                } else {
                    Section {
                        Text("\(provider.name) (not configured)")
                            .foregroundStyle(.secondary)
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Image(systemName: "cpu")
                Text(selectedModel.isEmpty ? "Select Model" : selectedModel)
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.caption2)
            }
            .font(.caption)
            .padding(.horizontal, 8)
            .padding(.vertical, 4)
            .background(Color(.controlBackgroundColor))
            .cornerRadius(6)
        }
        .menuStyle(.borderlessButton)
        .disabled(providers.isEmpty)
    }
}
