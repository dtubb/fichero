import SwiftUI

/// The chat surface's top-level tabs on the shared chrome (#3532 phase 1):
/// Conversation (messages), Sources (scoped documents), Knowledge (entities /
/// claims surfaced from the conversation). Compare + research/agent folds are
/// later slices. `chat = agent = workspace` (#3540).
enum ChatSurfaceTab: String, CaseIterable, Identifiable, SurfaceTab {
    case conversation
    case sources
    case knowledge
    case compare

    var id: String { rawValue }
    var title: String {
        switch self {
        case .conversation: return "Conversation"
        case .sources: return "Sources"
        case .knowledge: return "Knowledge"
        case .compare: return "Compare"
        }
    }
    var icon: String {
        switch self {
        case .conversation: return "bubble.left.and.bubble.right"
        case .sources: return "doc.on.doc"
        case .knowledge: return "point.3.connected.trianglepath.dotted"
        case .compare: return "rectangle.split.2x1"
        }
    }
    var help: String {
        switch self {
        case .conversation: return "Conversation — the chat messages"
        case .sources: return "Sources — documents scoped into this conversation"
        case .knowledge: return "Knowledge — entities and claims surfaced from this conversation"
        case .compare: return "Compare — run the same prompt across multiple agents/models side by side"
        }
    }
}

/// RAG-style chat view for conversing with documents
struct ChatView: View {
    let conversation: Conversation?
    @Binding var selectedDocuments: Set<String>
    var onConversationUpdated: (() -> Void)?
    /// Host-supplied attach targets for the composer paperclip (#2449 step 2).
    /// Defaults to empty, so a host without library context still gets the sheet.
    var attachContext: ChatAttachContext = .empty
    /// Optional conversation folder filter for hosts that scope chat threads
    /// to one workspace instead of the whole library.
    var conversationFolderPath: String?

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
    /// Document-scope sheet, presented from the composer pin menu's "Pin
    /// documents…" item (#3015 / #2449 hybrid step 3).
    @State var showAttachSheet: Bool = false

    // Provider/Model selection
    @State var providers: [LLMProvider] = []
    @State var selectedProvider: String = ""
    @State var selectedModel: String = ""

    @Environment(ChatServiceGenerated.self) var chatService
    @Environment(ConversationServiceGenerated.self) var conversationService
    /// Saved-workspace store (#3533) — a chat is ephemeral until saved on-demand.
    @Environment(WorkspaceStore.self) var workspaceStore

    /// Per-window chat tab (#3532), like the document inspector's @SceneStorage.
    @SceneStorage("chat.surfaceTab") private var chatTabRaw = ChatSurfaceTab.conversation.rawValue
    private var chatTab: ChatSurfaceTab { ChatSurfaceTab(rawValue: chatTabRaw) ?? .conversation }
    private var chatTabBinding: Binding<ChatSurfaceTab> {
        Binding(get: { chatTab }, set: { chatTabRaw = $0.rawValue })
    }

    init(
        conversation: Conversation?,
        selectedDocuments: Binding<Set<String>>,
        attachContext: ChatAttachContext = .empty,
        conversationFolderPath: String? = nil,
        onConversationUpdated: (() -> Void)? = nil
    ) {
        self.conversation = conversation
        self._selectedDocuments = selectedDocuments
        self.attachContext = attachContext
        self.conversationFolderPath = conversationFolderPath
        self.onConversationUpdated = onConversationUpdated
        self._currentConversation = State(initialValue: conversation ?? Conversation())
    }

    var body: some View {
        VStack(spacing: 0) {
            // View-specific toolbar at top (conversation switcher / provider).
            ChatViewToolbar(
                conversationTitle: currentConversation.title,
                conversations: visibleConversations,
                onSelectConversation: switchConversation,
                implicitScopeLabel: attachContext.implicitScopeLabel,
                selectedDocumentsCount: selectedDocuments.count,
                onClearDocuments: { selectedDocuments.removeAll() },
                providers: providers,
                selectedProvider: $selectedProvider,
                selectedModel: $selectedModel,
                onNewChat: startNewChat
            )

            // Shared top-tab chrome (#3532): Conversation / Sources / Knowledge.
            SurfaceTabBar(
                tabs: ChatSurfaceTab.allCases,
                selection: chatTabBinding,
                accessibilityID: "chatSurfaceTabBar"
            )

            Divider()

            switch chatTab {
            case .conversation: conversationTabContent
            case .sources: sourcesTabContent
            case .knowledge: knowledgeTabContent
            case .compare: compareTabContent
            }

            Divider()
            chatBottomBar
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

    private var visibleConversations: [Conversation] {
        Self.visibleConversations(
            conversationService.conversations,
            folderPath: conversationFolderPath
        )
    }

    /// Conversation tab — the messages plus the composer (#3532).
    private var conversationTabContent: some View {
        VStack(spacing: 0) {
            ChatMessagesList(
                conversation: currentConversation,
                isLoading: isLoading,
                errorMessage: errorMessage,
                inputText: $inputText
            )
            Divider()
            ChatInputView(
                inputText: $inputText,
                isLoading: isLoading,
                onSend: sendMessage
            ) {
                composerAttachMenu
            }
        }
    }

    /// Sources tab — the scoped-documents surface, reusing the existing
    /// `ChatInspector` inline (previously only shown in the attach sheet), bound
    /// to the same `selectedDocuments` so scope stays in one place (#3532).
    private var sourcesTabContent: some View {
        ChatInspector(
            selectedDocuments: $selectedDocuments,
            suggestedDocumentIDs: [],
            onAddSuggestedDocuments: nil
        )
    }

    /// Compare tab — the folded-in ModelComparison capability (#3532 slice 2):
    /// run one prompt across multiple agents/models side by side, now a facet of
    /// the one chat surface rather than a standalone top-level mode. Reuses
    /// `ModelComparisonView` verbatim (it is self-contained).
    private var compareTabContent: some View {
        ModelComparisonView()
    }

    /// Knowledge tab — entities/claims surfaced from the conversation. The chrome
    /// facet lands now; wiring the conversation-scoped KG content is a later
    /// #3532 slice (no chat-knowledge component to reuse yet).
    private var knowledgeTabContent: some View {
        ContentUnavailableView(
            "Knowledge",
            systemImage: "point.3.connected.trianglepath.dotted",
            description: Text("Entities and claims surfaced from this conversation will appear here.")
        )
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    /// Shared bottom mini-toolbar (#3532) — a per-tab status line plus the
    /// on-demand "Save as Workspace" action (#3533): a chat is ephemeral until
    /// the user saves it as a persistent workspace node (#3547 backend).
    private var chatBottomBar: some View {
        MiniToolbar {
            Text(chatBottomStatus)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer(minLength: 0)
            Button {
                saveAsWorkspace()
            } label: {
                Label("Save as Workspace", systemImage: "square.and.arrow.down")
            }
            .buttonStyle(.borderless)
            .controlSize(.small)
            .disabled(backendConversationId == nil)
            .help(backendConversationId == nil
                  ? "Send a message first, then save this chat as a workspace"
                  : "Save this chat as a reusable workspace node")
            .accessibilityIdentifier("chatSaveAsWorkspace")
        }
    }

    /// Persist the current conversation as a workspace via the store (#3533).
    private func saveAsWorkspace() {
        guard let conversationId = backendConversationId else { return }
        let title = currentConversation.title
        Task {
            await workspaceStore.save(
                conversationId: conversationId,
                title: title.isEmpty ? nil : title
            )
        }
    }

    private var chatBottomStatus: String {
        switch chatTab {
        case .conversation:
            let count = currentConversation.messages.count
            return "\(count) message\(count == 1 ? "" : "s")"
        case .sources:
            let count = selectedDocuments.count
            return count == 0 ? "No sources pinned" : "\(count) source\(count == 1 ? "" : "s")"
        case .knowledge:
            return "Knowledge"
        case .compare:
            return "Compare agents / models"
        }
    }

    /// Composer pin menu (#2449 hybrid step 3): the chat is already grounded on
    /// the current view implicitly, so this menu PINS a scope that persists as you
    /// navigate away — the open document, the current library view, or documents
    /// found via search. Every target routes through the same `attachScopedDocuments`
    /// path as drag-drop. Always present, so every width can pin context.
    @ViewBuilder
    private var composerAttachMenu: some View {
        Menu {
            if let docId = attachContext.openDocumentId {
                Button {
                    attachScopedDocuments([docId])
                } label: {
                    Label(
                        attachContext.openDocumentName.map { "Pin document — \($0)" } ?? "Pin this document",
                        systemImage: "doc"
                    )
                }
            }
            if attachContext.hasCurrentView {
                Button {
                    attachScopedDocuments(attachContext.currentViewDocumentIds)
                } label: {
                    Label(attachContext.currentViewLabel.map { "Pin — \($0)" } ?? "Pin current view", systemImage: "folder")
                }
            }
            if attachContext.hasHostTargets {
                Divider()
            }
            Button {
                showAttachSheet = true
            } label: {
                Label("Pin documents…", systemImage: "plus.magnifyingglass")
            }
        } label: {
            Image(systemName: "pin")
                .font(.title3)
                .foregroundColor(.secondary)
        }
        .menuIndicator(.hidden)
        .help("Pin documents to keep them in this chat as you navigate")
        .accessibilityLabel("Pin documents")
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
            .navigationTitle("Pin Documents")
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
