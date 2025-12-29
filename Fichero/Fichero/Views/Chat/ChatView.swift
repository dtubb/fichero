import SwiftUI
import UniformTypeIdentifiers

/// RAG-style chat view for conversing with documents
struct ChatView: View {
    let conversation: Conversation?
    @Binding var selectedDocuments: Set<String>
    var onConversationUpdated: (() -> Void)?

    @State private var currentConversation: Conversation
    @State private var inputText: String = ""
    @State private var isLoading: Bool = false
    @State private var errorMessage: String?
    @State private var isDropTargeted: Bool = false

    // Provider/Model selection
    @State private var providers: [LLMProvider] = []
    @State private var selectedProvider: String = ""
    @State private var selectedModel: String = ""

    private let chatService = ChatService()

    init(conversation: Conversation?, selectedDocuments: Binding<Set<String>>, onConversationUpdated: (() -> Void)? = nil) {
        self.conversation = conversation
        self._selectedDocuments = selectedDocuments
        self.onConversationUpdated = onConversationUpdated
        self._currentConversation = State(initialValue: conversation ?? Conversation())
    }

    var body: some View {
        VStack(spacing: 0) {
            // Toolbar
            chatToolbar

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
        }
    }

    private func loadConversation(_ id: String) async {
        do {
            let detail = try await chatService.getConversation(id)
            await MainActor.run {
                currentConversation = Conversation(
                    id: detail.id,
                    title: detail.title,
                    messages: detail.messages.map { $0.toChatMessage() },
                    documentScope: []
                )
            }
        } catch {
            NSLog("[ChatView] Failed to load conversation %@: %@", id, error.localizedDescription)
        }
    }

    // MARK: - Toolbar

    private var chatToolbar: some View {
        HStack {
            // Document scope indicator
            if selectedDocuments.isEmpty {
                Label("All documents", systemImage: "doc.on.doc")
                    .font(.caption)
                    .foregroundColor(.secondary)
            } else {
                Label("\(selectedDocuments.count) documents", systemImage: "checkmark.circle.fill")
                    .font(.caption)
                    .foregroundColor(.green)

                Button("Clear") {
                    selectedDocuments.removeAll()
                }
                .font(.caption)
                .buttonStyle(.plain)
                .foregroundColor(.accentColor)
            }

            Spacer()

            // Model picker
            modelPicker

            // New Chat button
            Button(action: startNewChat) {
                Label("New Chat", systemImage: "plus.bubble")
            }
            .buttonStyle(.bordered)
            .controlSize(.small)
        }
        .padding(.horizontal)
        .padding(.vertical, 8)
        .background(Color(.windowBackgroundColor))
        .onAppear {
            Task { await loadProviders() }
        }
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
                            .foregroundColor(.secondary)
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
            NSLog("[ChatView] Failed to load providers: %@", error.localizedDescription)
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
                        DispatchQueue.main.async {
                            selectedDocuments.insert(docId)
                            NSLog("[ChatView] Added document via drop: %@", docId)
                        }
                    }
                }
            } else if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        DispatchQueue.main.async {
                            selectedDocuments.insert(docId)
                            NSLog("[ChatView] Added document via drop: %@", docId)
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
        NSLog("[ChatView] Started new chat")
    }

    // MARK: - Messages View

    private var messagesView: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    if currentConversation.messages.isEmpty {
                        emptyStateView
                    } else {
                        ForEach(currentConversation.messages) { message in
                            MessageBubble(message: message)
                                .id(message.id)
                        }
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
            "Find mentions of specific people or places",
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

    // MARK: - Actions

    private func sendMessage() {
        guard !inputText.isEmpty else { return }

        let userMessage = ChatMessage(role: .user, content: inputText)
        currentConversation.messages.append(userMessage)
        let query = inputText
        inputText = ""
        errorMessage = nil
        isLoading = true

        Task {
            do {
                NSLog("[ChatView] Sending message: %@", query)

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

                NSLog("[ChatView] Got response with %d sources", response.sources.count)

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
                NSLog("[ChatView] Error: %@", error.localizedDescription)
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }
}

// MARK: - Chat Inspector View (Document Scope)

struct ChatInspectorView: View {
    @Binding var selectedDocuments: Set<String>

    @State private var scopedDocuments: [Document] = []  // Documents in scope with full info
    @State private var listSelection: Set<String> = []   // Selection within the list
    @State private var isLoading: Bool = false
    @State private var isDropTargeted: Bool = false

    // Search state
    @State private var searchText: String = ""
    @State private var searchResults: [Document] = []
    @State private var isSearching: Bool = false
    @State private var showSearchResults: Bool = false

    // Text extraction state
    @State private var isExtracting: Bool = false
    @State private var extractionResult: String?

    private let chatService = ChatService()

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Header with actions
            headerView

            Divider()

            // Search bar to find documents
            searchBarView

            Divider()

            // Main content: search results or scoped documents
            if showSearchResults && !searchText.isEmpty {
                searchResultsView
            } else if selectedDocuments.isEmpty {
                emptyStateView
            } else if isLoading {
                loadingView
            } else {
                scopedDocumentsView
            }
        }
        .background(Color(.windowBackgroundColor))
        .onDrop(of: [.text, .plainText], isTargeted: $isDropTargeted) { providers in
            handleDrop(providers: providers)
        }
        .overlay {
            if isDropTargeted {
                dropOverlay
            }
        }
        .onChange(of: selectedDocuments) { _, newValue in
            Task { await loadScopedDocuments() }
        }
        .task {
            await loadScopedDocuments()
        }
    }

    // MARK: - Header

    private var headerView: some View {
        HStack {
            Text("Chat Scope")
                .font(.headline)

            Spacer()

            if !selectedDocuments.isEmpty {
                // Select All button
                Button {
                    listSelection = selectedDocuments
                } label: {
                    Text("Select All")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .keyboardShortcut("a", modifiers: .command)

                // Remove selected button
                Button {
                    removeSelectedFromScope()
                } label: {
                    Image(systemName: "trash")
                        .font(.caption)
                }
                .buttonStyle(.plain)
                .disabled(listSelection.isEmpty)
                .keyboardShortcut(.delete, modifiers: [])

                // Clear all button
                Button {
                    selectedDocuments.removeAll()
                    listSelection.removeAll()
                } label: {
                    Text("Clear")
                        .font(.caption)
                }
                .buttonStyle(.plain)
            }
        }
        .padding()
        .background(Color(.windowBackgroundColor))
    }

    // MARK: - Search Bar

    private var searchBarView: some View {
        HStack {
            Image(systemName: "magnifyingglass")
                .foregroundColor(.secondary)

            TextField("Search documents to add...", text: $searchText)
                .textFieldStyle(.plain)
                .onSubmit {
                    Task { await performSearch() }
                }
                .onChange(of: searchText) { _, newValue in
                    if newValue.isEmpty {
                        showSearchResults = false
                        searchResults = []
                    } else {
                        showSearchResults = true
                        // Debounced search
                        Task {
                            try? await Task.sleep(nanoseconds: 300_000_000)
                            if searchText == newValue {
                                await performSearch()
                            }
                        }
                    }
                }

            if !searchText.isEmpty {
                Button {
                    searchText = ""
                    showSearchResults = false
                    searchResults = []
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
            }
        }
        .padding(8)
        .background(Color(.controlBackgroundColor))
    }

    // MARK: - Search Results

    private var searchResultsView: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Results header
            HStack {
                Text(isSearching ? "Searching..." : "\(searchResults.count) results")
                    .font(.caption)
                    .foregroundColor(.secondary)
                Spacer()
                Button("Add All") {
                    for doc in searchResults {
                        selectedDocuments.insert(doc.id)
                    }
                    searchText = ""
                    showSearchResults = false
                }
                .font(.caption)
                .buttonStyle(.plain)
                .disabled(searchResults.isEmpty)
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
            .background(Color(.controlBackgroundColor).opacity(0.5))

            if isSearching {
                ProgressView()
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else if searchResults.isEmpty {
                VStack(spacing: 8) {
                    Text("No documents found")
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                }
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List {
                    ForEach(searchResults) { doc in
                        HStack {
                            Image(systemName: doc.fileType?.icon ?? "doc")
                                .foregroundColor(.secondary)
                            Text(doc.name)
                                .lineLimit(1)
                            Spacer()
                            if selectedDocuments.contains(doc.id) {
                                Image(systemName: "checkmark.circle.fill")
                                    .foregroundColor(.green)
                            } else {
                                Button {
                                    selectedDocuments.insert(doc.id)
                                } label: {
                                    Image(systemName: "plus.circle")
                                        .foregroundColor(.accentColor)
                                }
                                .buttonStyle(.plain)
                            }
                        }
                        .contentShape(Rectangle())
                        .onTapGesture {
                            if !selectedDocuments.contains(doc.id) {
                                selectedDocuments.insert(doc.id)
                            }
                        }
                    }
                }
                .listStyle(.plain)
            }
        }
    }

    // MARK: - Scoped Documents View

    private var scopedDocumentsView: some View {
        VStack(alignment: .leading, spacing: 0) {
            // Scope info bar
            HStack(spacing: 8) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)

                Text("\(selectedDocuments.count) in scope")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if !listSelection.isEmpty {
                    Text("• \(listSelection.count) selected")
                        .font(.caption)
                        .foregroundColor(.accentColor)
                }

                Spacer()
            }
            .padding(.horizontal)
            .padding(.vertical, 6)
            .background(Color(.controlBackgroundColor).opacity(0.5))

            // Document list
            List(selection: $listSelection) {
                ForEach(scopedDocuments) { doc in
                    ScopedDocumentRow(document: doc)
                        .tag(doc.id)
                }
                .onDelete { indexSet in
                    let idsToRemove = indexSet.map { scopedDocuments[$0].id }
                    for id in idsToRemove {
                        selectedDocuments.remove(id)
                    }
                }
            }
            .listStyle(.plain)
        }
    }

    // MARK: - Empty State

    private var emptyStateView: some View {
        VStack(spacing: 12) {
            Image(systemName: "plus.rectangle.on.folder")
                .font(.system(size: 36))
                .foregroundColor(.secondary)

            Text("No documents in scope")
                .font(.subheadline)
                .foregroundColor(.secondary)

            Text("Search above or drag documents from Library to focus your chat.")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .padding(.horizontal)

            Divider()
                .padding(.vertical, 8)

            // Extract Text section
            VStack(spacing: 8) {
                Text("Document Maintenance")
                    .font(.caption)
                    .foregroundColor(.secondary)

                if isExtracting {
                    HStack {
                        ProgressView()
                            .scaleEffect(0.7)
                        Text("Extracting text...")
                            .font(.caption)
                    }
                } else {
                    Button {
                        Task { await extractAllText() }
                    } label: {
                        Label("Extract Text from All Documents", systemImage: "doc.text.magnifyingglass")
                            .font(.caption)
                    }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
                }

                if let result = extractionResult {
                    Text(result)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                        .multilineTextAlignment(.center)
                }
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private func extractAllText() async {
        isExtracting = true
        extractionResult = nil

        do {
            let response = try await chatService.extractText(documentIds: nil, force: false)
            await MainActor.run {
                extractionResult = "Done: \(response.extracted) extracted, \(response.skipped) skipped"
                isExtracting = false
            }
        } catch {
            await MainActor.run {
                extractionResult = "Error: \(error.localizedDescription)"
                isExtracting = false
            }
        }
    }

    // MARK: - Loading

    private var loadingView: some View {
        VStack {
            ProgressView()
            Text("Loading...")
                .font(.caption)
                .foregroundColor(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    // MARK: - Drop Overlay

    private var dropOverlay: some View {
        ZStack {
            Color.accentColor.opacity(0.15)
            VStack(spacing: 8) {
                Image(systemName: "plus.circle.fill")
                    .font(.title)
                    .foregroundColor(.accentColor)
                Text("Drop to add to scope")
                    .font(.subheadline)
                    .foregroundColor(.accentColor)
            }
        }
        .cornerRadius(8)
        .padding(4)
    }

    // MARK: - Actions

    private func removeSelectedFromScope() {
        for id in listSelection {
            selectedDocuments.remove(id)
        }
        listSelection.removeAll()
    }

    private func performSearch() async {
        guard !searchText.isEmpty else { return }

        isSearching = true

        do {
            // Search documents by name (simple filter for now)
            let allDocs: [Document] = try await APIClient.shared.get("/documents", query: ["limit": "100"])
            let filtered = allDocs.filter {
                $0.name.localizedCaseInsensitiveContains(searchText) &&
                $0.docType == .file
            }
            await MainActor.run {
                searchResults = filtered
                isSearching = false
            }
        } catch {
            NSLog("[ChatInspectorView] Search error: %@", error.localizedDescription)
            await MainActor.run {
                searchResults = []
                isSearching = false
            }
        }
    }

    private func handleDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            if provider.hasItemConformingToTypeIdentifier(UTType.text.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.text.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        DispatchQueue.main.async {
                            selectedDocuments.insert(docId)
                            NSLog("[ChatInspectorView] Added document via drop: %@", docId)
                        }
                    }
                }
            } else if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        DispatchQueue.main.async {
                            selectedDocuments.insert(docId)
                            NSLog("[ChatInspectorView] Added document via drop: %@", docId)
                        }
                    }
                }
            }
        }
        return true
    }

    private func loadScopedDocuments() async {
        guard !selectedDocuments.isEmpty else {
            await MainActor.run { scopedDocuments = [] }
            return
        }

        isLoading = true
        var loadedDocs: [Document] = []

        for docId in selectedDocuments {
            do {
                let doc: Document = try await APIClient.shared.get("/documents/\(docId)")
                loadedDocs.append(doc)
            } catch {
                NSLog("[ChatInspectorView] Failed to load doc %@: %@", docId, error.localizedDescription)
            }
        }

        await MainActor.run {
            scopedDocuments = loadedDocs.sorted { $0.name < $1.name }
            isLoading = false
            listSelection = listSelection.intersection(selectedDocuments)
        }
    }
}

// MARK: - Scoped Document Row

struct ScopedDocumentRow: View {
    let document: Document

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: document.fileType?.icon ?? "doc")
                .foregroundColor(.secondary)
                .frame(width: 16)

            VStack(alignment: .leading, spacing: 2) {
                Text(document.name)
                    .font(.subheadline)
                    .lineLimit(1)

                if let fileType = document.fileType {
                    Text(fileType.rawValue.capitalized)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
            }

            Spacer()
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }
}

// MARK: - Message Bubble

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

// MARK: - Preview

#Preview {
    ChatView(conversation: nil, selectedDocuments: .constant([]))
        .frame(width: 600, height: 500)
}
