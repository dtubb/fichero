import SwiftUI

/// RAG-style chat view for conversing with documents
struct ChatView: View {
    let conversation: Conversation?
    @Binding var selectedDocuments: Set<String>
    var onConversationUpdated: (() -> Void)?
    /// Host-supplied attach targets for the composer paperclip (#2449 step 2).
    /// Defaults to empty, so a host without library context still gets the sheet.
    var attachContext: ChatAttachContext = .empty

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
    /// Document-scope sheet, presented from the composer paperclip's "Add
    /// Documents…" item (#3015 / #2449 step 2).
    @State var showAttachSheet: Bool = false

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
        attachContext: ChatAttachContext = .empty,
        onConversationUpdated: (() -> Void)? = nil
    ) {
        self.conversation = conversation
        self._selectedDocuments = selectedDocuments
        self.attachContext = attachContext
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
                onSend: sendMessage
            ) {
                composerAttachMenu
            }
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

    /// Composer paperclip menu (#2449 step 2): attaches host-supplied context —
    /// the open document and/or the current library view — to the chat scope, plus
    /// the always-available "Add Documents…" search sheet. Every target routes
    /// through the same `attachScopedDocuments` path as drag-drop. Always present
    /// now (was a compact-only button), so every width can attach context.
    @ViewBuilder
    private var composerAttachMenu: some View {
        Menu {
            if let docId = attachContext.openDocumentId {
                Button {
                    attachScopedDocuments([docId])
                } label: {
                    Label(
                        attachContext.openDocumentName.map { "Open Document — \($0)" } ?? "Open Document",
                        systemImage: "doc"
                    )
                }
            }
            if attachContext.hasCurrentView {
                Button {
                    attachScopedDocuments(attachContext.currentViewDocumentIds)
                } label: {
                    Label(attachContext.currentViewLabel ?? "Current View", systemImage: "folder")
                }
            }
            if attachContext.hasHostTargets {
                Divider()
            }
            Button {
                showAttachSheet = true
            } label: {
                Label("Add Documents…", systemImage: "plus.magnifyingglass")
            }
        } label: {
            Image(systemName: "paperclip")
                .font(.title3)
                .foregroundColor(.secondary)
        }
        .menuIndicator(.hidden)
        .help("Attach documents to this chat")
        .accessibilityLabel("Attach context")
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
