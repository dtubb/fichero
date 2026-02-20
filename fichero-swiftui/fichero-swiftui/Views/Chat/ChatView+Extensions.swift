import SwiftUI
import UniformTypeIdentifiers
import OSLog

private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ChatView")

// MARK: - Data Loading

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
            logger.error("Failed to load conversation \(id): \(error.localizedDescription)")
        }
    }
    
    func loadProviders() async {
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
            logger.error("Failed to load providers: \(error.localizedDescription)")
            // Keep whatever providers we have - don't override with hardcoded fallback
        }
    }
}

// MARK: - Drop Support

extension ChatView {
    func handleDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            // Try to get document ID from drag
            if provider.hasItemConformingToTypeIdentifier(UTType.text.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.text.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        Task { @MainActor in
                            selectedDocuments.insert(docId)
                            logger.info("Added document via drop: \(docId)")
                        }
                    }
                }
            } else if provider.hasItemConformingToTypeIdentifier(UTType.plainText.identifier) {
                provider.loadItem(forTypeIdentifier: UTType.plainText.identifier, options: nil) { data, _ in
                    if let data = data as? Data, let docId = String(data: data, encoding: .utf8) {
                        Task { @MainActor in
                            selectedDocuments.insert(docId)
                            logger.info("Added document via drop: \(docId)")
                        }
                    }
                }
            }
        }
        return true
    }
}

// MARK: - Actions

extension ChatView {
    func startNewChat() {
        currentConversation = Conversation()
        selectedDocuments.removeAll()
        inputText = ""
        errorMessage = nil
        logger.info("Started new chat")
    }
    
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
                logger.info("Sending message: \(query)")
                
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
                
                logger.info("Got response with \(response.sources.count) sources")
                
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
                logger.error("Error: \(error.localizedDescription)")
                await MainActor.run {
                    errorMessage = error.localizedDescription
                    isLoading = false
                }
            }
        }
    }
}
