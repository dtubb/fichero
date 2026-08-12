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

    // Document scope (#2449 hybrid): the implicit current-view label (what the
    // chat is grounded on by default) + the count of PINNED documents layered on
    // top via the paperclip.
    let implicitScopeLabel: String?
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
            ChatConversationMenu(
                conversationTitle: conversationTitle,
                conversations: conversations,
                onSelectConversation: onSelectConversation
            )
            .equatable()

            Spacer(minLength: 8)

            // Trailing: the active grounding — implicit current-view scope +
            // pinned documents (#2449 hybrid) — then the model picker.
            if implicitScopeLabel != nil || selectedDocumentsCount > 0 {
                scopeIndicator
            }
            ChatModelPicker(
                providers: providers,
                selectedProvider: $selectedProvider,
                selectedModel: $selectedModel
            )
            .equatable()
        })
    }

    /// The active chat grounding (#2449 hybrid): the implicit current-view scope
    /// (an eye — follows what you're looking at) plus the pinned documents (a
    /// pin — kept as you navigate), so the user can always see what the chat is
    /// grounded on.
    @ViewBuilder
    private var scopeIndicator: some View {
        HStack(spacing: 8) {
            if let implicitScopeLabel {
                Label(implicitScopeLabel, systemImage: "eye")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
                    .help("Grounded on your current view: \(implicitScopeLabel)")
            }
            if selectedDocumentsCount > 0 {
                HStack(spacing: 4) {
                    Label("\(selectedDocumentsCount)", systemImage: "pin.fill")
                        .font(.caption)
                        .foregroundStyle(.orange)
                    Button("Clear", action: onClearDocuments)
                        .font(.caption)
                        .buttonStyle(.plain)
                        .foregroundColor(.accentColor)
                }
                .help("\(selectedDocumentsCount) pinned document(s) — kept in scope as you navigate")
            }
        }
    }
}

// MARK: - Equatable menu subtrees (#23)

// Both menus are AppKit-backed popups (NSPopUpButton); re-syncing an NSMenu
// costs real main-thread time. Every PAGE FLIP changes only the toolbar's
// implicit scope label, but that re-evaluated the whole toolbar body and
// re-synced both menus — a 738ms NSPopUpButtonCell stall per flip
// (2026-08-12). Each menu is its own Equatable view so SwiftUI skips its
// body unless the data it actually renders changed. `.equatable()` is
// load-bearing: the @Binding/closure fields defeat SwiftUI's reflective
// comparison, so without it the views compare unequal every time.

private struct ChatConversationMenu: View, Equatable {
    let conversationTitle: String
    let conversations: [Conversation]
    let onSelectConversation: (Conversation) -> Void

    nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.conversationTitle == rhs.conversationTitle
            && lhs.conversations.map(\.id) == rhs.conversations.map(\.id)
            && lhs.conversations.map(\.title) == rhs.conversations.map(\.title)
    }

    var body: some View {
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
}

private struct ChatModelPicker: View, Equatable {
    let providers: [LLMProvider]
    @Binding var selectedProvider: String
    @Binding var selectedModel: String

    nonisolated static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.selectedProvider == rhs.selectedProvider
            && lhs.selectedModel == rhs.selectedModel
            && lhs.providers == rhs.providers
    }

    var body: some View {
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
