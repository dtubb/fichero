import SwiftUI

/// RAG-style chat view for conversing with documents
struct ChatView: View {
    let conversation: Conversation?
    @Binding var selectedDocuments: Set<String>
    var onConversationUpdated: (() -> Void)?

    @State var currentConversation: Conversation
    // Tracks the backend-confirmed conversation ID. Nil until the first
    // successful response — the backend creates the conversation on first POST
    // and returns its ID. We must NOT send a client-generated UUID as
    // conversation_id or the backend returns 404.
    @State var backendConversationId: String?
    @State var inputText: String = ""
    @State var isLoading: Bool = false
    @State var errorMessage: String?
    @State var isDropTargeted: Bool = false
    /// Compact document-scope sheet, presented from the composer paperclip (#3015).
    @State var showAttachSheet: Bool = false
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass

    // Provider/Model selection
    @State var providers: [LLMProvider] = []
    @State var selectedProvider: String = ""
    @State var selectedModel: String = ""

    /// Recent conversations backing the header title menu (#2449).
    @State var conversations: [Conversation] = []

    @EnvironmentObject var chatService: ChatServiceGenerated
    @EnvironmentObject var conversationService: ConversationServiceGenerated

    init(
        conversation: Conversation?,
        selectedDocuments: Binding<Set<String>>,
        onConversationUpdated: (() -> Void)? = nil
    ) {
        self.conversation = conversation
        self._selectedDocuments = selectedDocuments
        self.onConversationUpdated = onConversationUpdated
        self._currentConversation = State(initialValue: conversation ?? Conversation())
    }

    var body: some View {
        VStack(spacing: 0) {
            // View-specific toolbar at top
            ChatViewToolbar(
                conversationTitle: currentConversation.title,
                conversations: conversations,
                onSelectConversation: switchConversation,
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
                isLoading: isLoading,
                errorMessage: errorMessage,
                inputText: $inputText
            )

            Divider()

            // Input area
            ChatInputView(
                inputText: $inputText,
                isLoading: isLoading,
                onSend: sendMessage,
                // Compact has no side inspector to drop onto — surface the same
                // document-scope surface as a sheet via a composer button (#3015).
                onAttach: ContentView.shouldUseCompactNavigationFlow(
                    horizontalSizeClass: horizontalSizeClass
                ) ? { showAttachSheet = true } : nil
            )
        }
        .sheet(isPresented: $showAttachSheet) {
            chatAttachSheet
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
            // Load providers + the recent-conversation list for the title menu (#2449)
            await loadProviders()
            await loadConversations()
        }
    }

    /// The document-scope surface, presented as a sheet on compact width so a
    /// phone can add documents without the side inspector or drag-drop. Reuses
    /// the existing `ChatInspector` (search + add) bound to the same
    /// `selectedDocuments`, so adds route through the same scope — no parallel
    /// picker (#3015). Suggestions need library context ChatView lacks, so the
    /// sheet is search-driven (empty suggestions).
    @ViewBuilder
    private var chatAttachSheet: some View {
        NavigationStack {
            ChatInspector(
                selectedDocuments: $selectedDocuments,
                suggestedDocumentIDs: [],
                onAddSuggestedDocuments: nil
            )
            .navigationTitle("Add Documents")
            #if !os(macOS)
            .navigationBarTitleDisplayMode(.inline)
            #endif
            .toolbar {
                ToolbarItem(placement: .confirmationAction) {
                    Button("Done") { showAttachSheet = false }
                }
            }
        }
    }
}

// MARK: - Preview

#Preview {
    ChatView(
        conversation: nil,
        selectedDocuments: .constant([])
    )
    .frame(width: 600, height: 500)
}
