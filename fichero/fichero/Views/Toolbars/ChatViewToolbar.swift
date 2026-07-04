import SwiftUI

/// Toolbar for Chat view with model selection and chat controls.
///
/// Xcode-chat layout (#2449): a New-conversation icon on the leading edge, the
/// conversation title as a center menu that jumps to earlier conversations (it
/// doubles as the history affordance), and the model picker + a compact scope
/// chip trailing. The always-on "All documents" label is dropped — the default
/// scope is implied, and the header stays clean ("the old one was too much").
struct ChatViewToolbar: View {
    // Conversation header
    let conversationTitle: String
    let conversations: [Conversation]
    let onSelectConversation: (Conversation) -> Void

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
        // shared toolbar language.
        MiniToolbar(content: {
            // Leading: New conversation (Xcode top-left).
            Button(action: onNewChat) {
                Image(systemName: "square.and.pencil")
            }
            .buttonStyle(.plain)
            .help("New conversation")
            .accessibilityLabel("New conversation")

            Spacer(minLength: 8)

            // Center: the conversation title IS a menu that jumps to earlier
            // conversations (#2449) — also the history affordance.
            conversationTitleMenu

            Spacer(minLength: 8)

            // Trailing: compact scope chip (only when documents are scoped) + model picker.
            if selectedDocumentsCount > 0 {
                scopeChip
            }
            modelPicker
        })
    }

    private var conversationTitleMenu: some View {
        Menu {
            if conversations.isEmpty {
                Text("No earlier conversations")
            } else {
                Section("Earlier Conversations") {
                    ForEach(conversations) { conv in
                        Button {
                            onSelectConversation(conv)
                        } label: {
                            Text(conv.title.isEmpty ? "Untitled" : conv.title)
                        }
                    }
                }
            }
        } label: {
            HStack(spacing: 4) {
                Text(conversationTitle.isEmpty ? "New Chat" : conversationTitle)
                    .font(.headline)
                    .lineLimit(1)
                Image(systemName: "chevron.down")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        }
        .menuStyle(.borderlessButton)
        .menuIndicator(.hidden)
        .fixedSize()
        .help("Switch conversation")
        .accessibilityLabel("Conversation history")
    }

    private var scopeChip: some View {
        HStack(spacing: 4) {
            Label("\(selectedDocumentsCount)", systemImage: "checkmark.circle.fill")
                .font(.caption)
                .foregroundStyle(.green)
            Button("Clear", action: onClearDocuments)
                .font(.caption)
                .buttonStyle(.plain)
                .foregroundColor(.accentColor)
        }
        .help("\(selectedDocumentsCount) document(s) in chat scope")
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
