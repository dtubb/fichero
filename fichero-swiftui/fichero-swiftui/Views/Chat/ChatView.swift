import SwiftUI

/// RAG-style chat view for conversing with documents
struct ChatView: View {
    let conversation: Conversation?
    @Binding var selectedDocuments: Set<String>
    var onConversationUpdated: (() -> Void)?
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    @State var currentConversation: Conversation
    @State var inputText: String = ""
    @State var isLoading: Bool = false
    @State var errorMessage: String?
    @State var isDropTargeted: Bool = false

    // Provider/Model selection
    @State var providers: [LLMProvider] = []
    @State var selectedProvider: String = ""
    @State var selectedModel: String = ""

    @EnvironmentObject var chatService: ChatServiceGenerated
    @EnvironmentObject var conversationService: ConversationServiceGenerated

    init(
        conversation: Conversation?,
        selectedDocuments: Binding<Set<String>>,
        onConversationUpdated: (() -> Void)? = nil,
        displayMode: ViewDisplayMode = .icon
    ) {
        self.conversation = conversation
        self._selectedDocuments = selectedDocuments
        self.onConversationUpdated = onConversationUpdated
        self.displayMode = displayMode
        self._currentConversation = State(initialValue: conversation ?? Conversation())
    }

    var body: some View {
        VStack(spacing: 0) {
            // View-specific toolbar at top
            ChatViewToolbar(
                selectedDocumentsCount: selectedDocuments.count,
                onClearDocuments: { selectedDocuments.removeAll() },
                providers: providers,
                selectedProvider: $selectedProvider,
                selectedModel: $selectedModel,
                onNewChat: startNewChat
            )

            Divider()

            // Messages list
            ChatMessagesList(
                conversation: currentConversation,
                displayMode: displayMode,
                isLoading: isLoading,
                errorMessage: errorMessage,
                inputText: $inputText
            )

            Divider()

            // Input area
            ChatInputView(
                inputText: $inputText,
                isLoading: isLoading,
                onSend: sendMessage
            )
        }
        .onDrop(of: [.text, .plainText], isTargeted: $isDropTargeted) { providers in
            handleDrop(providers: providers)
        }
        .overlay {
            if isDropTargeted {
                ChatDropOverlay()
            }
        }
        .task {
            // Load full conversation if we have an ID but no messages
            if let conv = conversation, conv.messages.isEmpty {
                await loadConversation(conv.id)
            }
            // Load providers
            await loadProviders()
        }
    }
}

// MARK: - Preview

#Preview {
    ChatView(
        conversation: nil,
        selectedDocuments: .constant([]),
        displayMode: .icon
    )
    .frame(width: 600, height: 500)
}
