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

    /// Load the recent-conversation list that backs the header title menu
    /// (#2449 Xcode-style: the title is a menu to jump to earlier conversations).
    func loadConversations() async {
        do {
            let list = try await conversationService.getConversationsForSidebar()
            await MainActor.run { conversations = list }
        } catch {
            logger.error("Failed to load conversations: \(error.localizedDescription)")
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

// MARK: - Attach Context (#2449 step 2)

/// The attachable context the chat host (e.g. ContentView) offers the composer
/// paperclip. ChatView deliberately has no library context of its own, so the
/// host supplies the resolvable targets; each non-empty one becomes a paperclip
/// menu item that adds its document ids to the chat scope via the same
/// `attachScopedDocuments` path as drag-drop. Defaults are empty, so hosts
/// without library context (e.g. ResearchChatPane) simply get the always-present
/// "Add Documents…" search sheet.
struct ChatAttachContext {
    /// The currently-open document (attach → chat with that document).
    var openDocumentId: String?
    var openDocumentName: String?
    /// Documents in the current library view / folder, with a display label.
    var currentViewLabel: String?
    var currentViewDocumentIds: [String] = []

    static let empty = ChatAttachContext()

    var hasOpenDocument: Bool { openDocumentId != nil }
    var hasCurrentView: Bool { !currentViewDocumentIds.isEmpty }
    var hasHostTargets: Bool { hasOpenDocument || hasCurrentView }

    // MARK: - Implicit grounding (#2449 hybrid)

    /// The document ids the CURRENT VIEW grounds the chat on implicitly, with no
    /// pin needed (#2449 hybrid): the focused document if one is open, otherwise
    /// the documents in the current view / folder / search. Empty ⇒ ground on the
    /// whole library.
    var implicitScopeIds: [String] {
        if let openDocumentId {
            return [openDocumentId]
        }
        return currentViewDocumentIds
    }

    /// A short human label for the implicit current-view scope, shown so the user
    /// can see what the chat is grounded on. `nil` ⇒ whole library.
    var implicitScopeLabel: String? {
        if openDocumentId != nil {
            return openDocumentName ?? "This document"
        }
        return currentViewLabel
    }

    var hasImplicitScope: Bool { !implicitScopeIds.isEmpty }
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

    /// Jump to an earlier conversation from the header title menu (#2449). Sets
    /// `backendConversationId` so the next message CONTINUES this thread (the
    /// backend 404s on a client-generated id), shows its title immediately, then
    /// loads its messages.
    func switchConversation(_ conversation: Conversation) {
        guard conversation.id != currentConversation.id else { return }
        currentConversation = conversation
        backendConversationId = conversation.id
        selectedDocuments.removeAll()
        inputText = ""
        errorMessage = nil
        logger.info("Switched to conversation \(conversation.id)")
        Task { await loadConversation(conversation.id) }
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

                // Hybrid grounding (#2449): the CURRENT VIEW's implicit scope
                // (the doc/folder/search you're looking at — no attach needed)
                // UNION the PINNED documents from the paperclip (which persist
                // across navigation). Empty ⇒ nil ⇒ ground on the whole library.
                let groundingIds = Set(attachContext.implicitScopeIds).union(selectedDocuments)

                // Call the RAG API — pass backendConversationId (nil for first
                // message). The backend creates the conversation on first POST
                // and returns its ID; passing a client-generated UUID returns 404.
                let response = try await chatService.chat(
                    message: query,
                    conversationId: backendConversationId,
                    documentIds: groundingIds.isEmpty ? nil : Array(groundingIds),
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
                // Refresh the header title menu so a newly-created conversation
                // (and its backend-assigned title) appears in the jump list (#2449).
                await loadConversations()
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
