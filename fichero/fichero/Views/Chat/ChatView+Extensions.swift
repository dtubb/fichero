import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "ChatView")

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

// MARK: - Document Scope

/// Pure chat-scope mutation shared by every attach entry point (drop, and the
/// compact composer attach button) so they reach scope the same way (#3015).
enum ChatDocumentScope {
    /// Union `ids` into `scope`, de-duplicated; blank ids are ignored.
    static func attaching(_ ids: [String], to scope: Set<String>) -> Set<String> {
        var next = scope
        for id in ids where !id.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            next.insert(id)
        }
        return next
    }
}

// MARK: - Drop Support

extension ChatView {
    /// The single scope-attach path. The onDrop closure and the composer attach
    /// button both route document ids through here — no divergent handler (#3015).
    func attachScopedDocuments(_ ids: [String]) {
        selectedDocuments = ChatDocumentScope.attaching(ids, to: selectedDocuments)
        logger.info("Attached \(ids.count) document(s) to chat scope")
    }

    func handleDrop(providers: [NSItemProvider]) -> Bool {
        for provider in providers {
            guard let typeIdentifier = ChatDocumentDropPayload.firstSupportedTypeIdentifier(in: provider) else {
                continue
            }

            provider.loadItem(forTypeIdentifier: typeIdentifier, options: nil) { item, _ in
                guard let docId = ChatDocumentDropPayload.documentID(from: item) else {
                    return
                }

                Task { @MainActor in
                    attachScopedDocuments([docId])
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
        backendConversationId = nil
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

                // Call the RAG API — pass backendConversationId (nil for first
                // message). The backend creates the conversation on first POST
                // and returns its ID; passing a client-generated UUID returns 404.
                let response = try await chatService.chat(
                    message: query,
                    conversationId: backendConversationId,
                    documentIds: selectedDocuments.isEmpty ? nil : Array(selectedDocuments),
                    includeSources: true,
                    maxSources: 5,
                    provider: selectedProvider,
                    model: selectedModel
                )

                logger.info("Got response with \(response.sources.count) sources")

                // Convert API sources to local model
                let sources = response.sources.map { $0.toDocumentSource() }

                // Capture what the library search retrieved for this message.
                let retrieval = RetrievalInfo(
                    documentCount: response.documentCount,
                    contextCount: response.contextCount,
                    kgClaimsUsed: response.kgClaimsUsed,
                    kgEntitiesUsed: response.kgEntitiesUsed
                )

                // Create assistant message
                let assistantMessage = ChatMessage(
                    role: .assistant,
                    content: response.message,
                    sources: sources,
                    retrieval: retrieval
                )

                await MainActor.run {
                    backendConversationId = response.conversationId
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
