import SwiftUI
import UniformTypeIdentifiers
import OSLog

/// RAG-style chat view for conversing with documents
struct ChatView: View {
    let conversation: Conversation?
    @Binding var selectedDocuments: Set<String>
    var onConversationUpdated: (() -> Void)?
    let displayMode: ViewDisplayMode  // Universal view mode from toolbar

    @State private var currentConversation: Conversation
    @State private var inputText: String = ""
    @State private var isLoading: Bool = false
    @State private var errorMessage: String?
    @State private var isDropTargeted: Bool = false

    // Provider/Model selection
    @State private var providers: [LLMProvider] = []
    @State private var selectedProvider: String = ""
    @State private var selectedModel: String = ""

    @EnvironmentObject var chatService: ChatServiceGenerated
    @EnvironmentObject var conversationService: ConversationServiceGenerated
    private static let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ChatView")

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
            messagesView

            Divider()

            // Input area
            inputArea
        }
        .onDrop(of: [.text, .plainText], isTargeted: $isDropTargeted) { providers in
            handleDrop(providers: providers)
        }
        .overlay {
            if isDropTargeted {
                dropOverlay
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

// MARK: - View Components & Loading

extension ChatView {
    func loadConversation(_ id: String) async {
        do {
            let detail = try await conversationService.getConversation(id)
            await MainActor.run {
                currentConversation = Conversation(
                    id: detail.id,
                    title: detail.title,
                    messages: detail.messages.map { $0.toChatMessage() },
                    documentScope: []
                )
            }
        } catch {
            Self.logger.error("Failed to load conversation \(id): \(error.localizedDescription)")
        }
    }

    // MARK: - Provider Management

    private func loadProviders() async {
        do {
            let fetchedProviders = try await chatService.listProviders()
            await MainActor.run {
                providers = fetchedProviders

                // Select first available provider/model if none selected or current is unavailable
                let currentAvailable = fetchedProviders.first(where: { $0.id == selectedProvider && $0.available })
                if currentAvailable == nil, let firstAvailable = fetchedProviders.first(where: { $0.available }) {
                    selectedProvider = firstAvailable.id
                    selectedModel = firstAvailable.models.first ?? ""
                }
            }
        } catch {
            Self.logger.error("Failed to load providers: \(error.localizedDescription)")
            // Keep whatever providers we have - don't override with hardcoded fallback
        }
    }

    // MARK: - Drop Support

    private var dropOverlay: some View {
        ZStack {
            Color.accentColor.opacity(0.1)
            VStack(spacing: 8) {
                Image(systemName: "plus.circle.fill")
                    .font(.largeTitle)
                    .foregroundColor(.accentColor)
                Text("Drop documents to add to chat scope")
                    .font(.headline)
                    .foregroundColor(.accentColor)
            }
        }
        .cornerRadius(12)
        .padding()
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            // Try to get document ID from drag
            if provider.hasItemConformingToTypeIdentifier(UTType.text.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.text.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        Task { @MainActor in
                            selectedDocuments.insert(docId)
                            Self.logger.info("Added document via drop: \(docId)")
                        }
                    }
                }
            } else if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        Task { @MainActor in
                            selectedDocuments.insert(docId)
                            Self.logger.info("Added document via drop: \(docId)")
                        }
                    }
                }
            }
        }
        return true
    }

    // MARK: - Actions

    private func startNewChat() {
        currentConversation = Conversation()
        selectedDocuments.removeAll()
        inputText = ""
        errorMessage = nil
        Self.logger.info("Started new chat")
    }

    // MARK: - Messages View

    private var messagesView: some View {
        Group {
            if currentConversation.messages.isEmpty {
                emptyStateView
            } else {
                switch displayMode {
                case .icon:
                    messagesIconView
                case .list:
                    messagesBubbleView
                case .table:
                    messagesTableView
                case .map:
                    messagesMapView
                }
            }
        }
    }

    private var messagesIconView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVGrid(
                    columns: [GridItem(.adaptive(minimum: 200, maximum: 280))],
                    spacing: 16
                ) {
                    ForEach(currentConversation.messages) { message in
                        MessageCard(message: message)
                            .id(message.id)
                    }
                }
                .padding()

                if isLoading {
                    loadingIndicator
                }

                if let error = errorMessage {
                    errorView(error)
                }
            }
            .onChange(of: currentConversation.messages.count) { _, _ in
                if let lastMessage = currentConversation.messages.last {
                    withAnimation {
                        proxy.scrollTo(lastMessage.id, anchor: .bottom)
                    }
                }
            }
        }
        .background(Color(.textBackgroundColor))
    }

    private var messagesMapView: some View {
        GeometryReader { geometry in
            ScrollView([.horizontal, .vertical]) {
                ZStack {
                    // Grid background
                    ChatMapGrid()
                        .stroke(Color.gray.opacity(0.2), lineWidth: 0.5)
                        .allowsHitTesting(false)

                    // Message cards positioned on canvas
                    ForEach(Array(currentConversation.messages.enumerated()), id: \.element.id) { index, message in
                        MessageMapCard(message: message)
                            .position(messagePosition(for: index, role: message.role, in: geometry.size))
                    }

                    if isLoading {
                        loadingIndicator
                            .position(x: geometry.size.width / 2, y: geometry.size.height - 50)
                    }
                }
                .frame(width: max(geometry.size.width, 1000), height: max(geometry.size.height, 600))
            }
        }
        .background(Color(.textBackgroundColor))
    }

    /// Position messages in a flowing conversation layout
    private func messagePosition(for index: Int, role: ChatRole, in size: CGSize) -> CGPoint {
        let ySpacing: CGFloat = 120
        let xOffset: CGFloat = role == .user ? size.width * 0.7 : size.width * 0.3
        return CGPoint(x: min(max(xOffset, 150), size.width - 150), y: CGFloat(index) * ySpacing + 80)
    }

    private var messagesBubbleView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    ForEach(currentConversation.messages) { message in
                        MessageBubble(message: message)
                            .id(message.id)
                    }

                    if isLoading {
                        loadingIndicator
                    }

                    if let error = errorMessage {
                        errorView(error)
                    }
                }
                .padding()
            }
            .onChange(of: currentConversation.messages.count) { _, _ in
                if let lastMessage = currentConversation.messages.last {
                    withAnimation {
                        proxy.scrollTo(lastMessage.id, anchor: .bottom)
                    }
                }
            }
        }
        .background(Color(.textBackgroundColor))
    }

    private var messagesTableView: some View {
        VStack(spacing: 0) {
            Table(currentConversation.messages) {
                TableColumn("Role") { message in
                    Text(message.role == .user ? "User" : "Assistant")
                        .font(.caption)
                        .foregroundColor(.secondary)
                }
                .width(min: 60, ideal: 80)

                TableColumn("Content") { message in
                    Text(message.content)
                        .lineLimit(3)
                }

                TableColumn("Sources") { message in
                    if let sources = message.sources, !sources.isEmpty {
                        Text("\(sources.count) source(s)")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else {
                        Text("—")
                            .foregroundColor(.secondary)
                    }
                }
                .width(min: 80, ideal: 100)
            }

            if isLoading {
                Divider()
                loadingIndicator
                    .padding()
            }

            if let error = errorMessage {
                Divider()
                errorView(error)
                    .padding()
            }
        }
        .background(Color(.textBackgroundColor))
    }

    private func errorView(_ message: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle")
                .foregroundColor(.orange)
            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .padding()
        .background(Color.orange.opacity(0.1))
        .cornerRadius(8)
    }

    private var emptyStateView: some View {
        VStack(spacing: 16) {
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text("Chat with your documents")
                .font(.headline)

            Text("Ask questions about your documents and get answers with source citations.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 300)

            VStack(alignment: .leading, spacing: 8) {
                Text("Try asking:")
                    .font(.caption)
                    .foregroundColor(.secondary)

                ForEach(sampleQuestions, id: \.self) { question in
                    Button {
                        inputText = question
                    } label: {
                        Text(question)
                            .font(.subheadline)
                            .foregroundColor(.accentColor)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding()
            .background(Color(.controlBackgroundColor))
            .cornerRadius(8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private var sampleQuestions: [String] {
        [
            "What are the main themes in these documents?",
            "Summarize the key points from the letters",
            "Find mentions of specific people or places"
        ]
    }

    private var loadingIndicator: some View {
        HStack(spacing: 8) {
            ProgressView()
                .scaleEffect(0.8)
            Text("Searching and generating response...")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .padding()
    }

    // MARK: - Input Area

    private var inputArea: some View {
        HStack(spacing: 12) {
            TextField("Ask a question about your documents...", text: $inputText, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...5)
                .onSubmit {
                    sendMessage()
                }

            Button(action: sendMessage) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title2)
                    .foregroundColor(inputText.isEmpty ? .secondary : .accentColor)
            }
            .buttonStyle(.plain)
            .disabled(inputText.isEmpty || isLoading)
            .keyboardShortcut(.return, modifiers: [])
        }
        .padding()
        .background(Color(.windowBackgroundColor))
    }
}

// MARK: - Actions

extension ChatView {
    func sendMessage() {
        guard !inputText.isEmpty else { return }

        let userMessage = ChatMessage(role: .user, content: inputText)
        currentConversation.messages.append(userMessage)
        let query = inputText
        inputText = ""
        errorMessage = nil
        isLoading = true

        Task { @MainActor in
            do {
                Self.logger.info("Sending message: \(query)")

                // Call the RAG API
                let response = try await chatService.chat(
                    message: query,
                    conversationId: currentConversation.id,
                    documentIds: selectedDocuments.isEmpty ? nil : Array(selectedDocuments),
                    includeSources: true,
                    maxSources: 5,
                    provider: selectedProvider,
                    model: selectedModel
                )

                Self.logger.info("Got response with \(response.sources.count) sources")

                // Convert API sources to local model
                let sources = response.sources.map { $0.toDocumentSource() }

                // Create assistant message
                let assistantMessage = ChatMessage(
                    role: .assistant,
                    content: response.message,
                    sources: sources
                )

                await MainActor.run {
                    currentConversation.messages.append(assistantMessage)
                    isLoading = false
                    // Notify that conversation was updated (for sidebar refresh)
                    onConversationUpdated?()
                }
            } catch {
                Self.logger.error("Error: \(error.localizedDescription)")
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }
}

// MARK: - Message Bubble

/// Displays a single chat message in a bubble format
struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 8) {
            HStack {
                if message.role == .user { Spacer() }

                VStack(alignment: .leading, spacing: 8) {
                    Text(message.content)
                        .padding(12)
                        .background(bubbleBackground)
                        .foregroundColor(message.role == .user ? .white : .primary)
                        .cornerRadius(16)

                    // Sources (for assistant messages)
                    if let sources = message.sources, !sources.isEmpty {
                        sourcesView(sources)
                    }
                }
                .frame(maxWidth: 500, alignment: message.role == .user ? .trailing : .leading)

                if message.role == .assistant { Spacer() }
            }
        }
    }

    private var bubbleBackground: Color {
        message.role == .user ? Color.accentColor : Color(.controlBackgroundColor)
    }

    @ViewBuilder
    private func sourcesView(_ sources: [DocumentSource]) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text("Sources")
                .font(.caption2)
                .foregroundColor(.secondary)

            ForEach(sources) { source in
                HStack(spacing: 6) {
                    Image(systemName: "doc.text")
                        .font(.caption2)
                        .foregroundColor(.secondary)

                    Text(source.documentName)
                        .font(.caption)
                        .foregroundColor(.accentColor)

                    Spacer()

                    Text("\(Int(source.relevanceScore * 100))%")
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                .padding(.horizontal, 8)
                .padding(.vertical, 4)
                .background(Color(.controlBackgroundColor))
                .cornerRadius(4)
            }
        }
        .padding(.leading, 12)
    }
}

// MARK: - Message Card (for Icon view)

/// Card representation of a chat message for Icon/Grid view
private struct MessageCard: View {
    let message: ChatMessage

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Role badge
            HStack {
                Image(systemName: message.role == .user ? "person.fill" : "brain.head.profile")
                    .foregroundColor(message.role == .user ? .accentColor : .purple)
                Text(message.role == .user ? "You" : "Assistant")
                    .font(.caption)
                    .fontWeight(.medium)
                Spacer()
            }

            // Content preview
            Text(message.content)
                .font(.subheadline)
                .foregroundColor(.primary)
                .lineLimit(4)

            // Sources indicator
            if let sources = message.sources, !sources.isEmpty {
                HStack(spacing: 4) {
                    Image(systemName: "doc.text")
                        .font(.caption2)
                    Text("\(sources.count) source(s)")
                        .font(.caption2)
                }
                .foregroundColor(.secondary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(message.role == .user ? Color.accentColor.opacity(0.1) : Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color(.separatorColor), lineWidth: 1)
        )
    }
}

// MARK: - Message Map Card (for Map view)

/// Card representation for spatial map view
private struct MessageMapCard: View {
    let message: ChatMessage

    var body: some View {
        VStack(spacing: 6) {
            // Role icon
            Image(systemName: message.role == .user ? "person.fill" : "brain.head.profile")
                .font(.title2)
                .foregroundColor(message.role == .user ? .accentColor : .purple)
                .frame(width: 40, height: 40)
                .background((message.role == .user ? Color.accentColor : Color.purple).opacity(0.15))
                .clipShape(Circle())

            // Content preview
            Text(message.content)
                .font(.caption)
                .lineLimit(3)
                .multilineTextAlignment(.center)
                .frame(width: 140)

            // Sources badge
            if let sources = message.sources, !sources.isEmpty {
                Text("\(sources.count) sources")
                    .font(.caption2)
                    .foregroundColor(.white)
                    .padding(.horizontal, 6)
                    .padding(.vertical, 2)
                    .background(Color.gray)
                    .clipShape(Capsule())
            }
        }
        .padding(10)
        .frame(width: 160, height: 130)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(message.role == .user ? Color.accentColor : Color.purple, lineWidth: 2)
        )
        .shadow(color: .black.opacity(0.1), radius: 2, x: 0, y: 1)
    }
}

// MARK: - Chat Map Grid

private struct ChatMapGrid: Shape {
    func path(in rect: CGRect) -> Path {
        var path = Path()
        let spacing: CGFloat = 40

        var xPos = spacing
        while xPos < rect.width {
            path.move(to: CGPoint(x: xPos, y: 0))
            path.addLine(to: CGPoint(x: xPos, y: rect.height))
            xPos += spacing
        }

        var yPos = spacing
        while yPos < rect.height {
            path.move(to: CGPoint(x: 0, y: yPos))
            path.addLine(to: CGPoint(x: rect.width, y: yPos))
            yPos += spacing
        }

        return path
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
