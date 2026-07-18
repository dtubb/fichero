import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for saved agent workspaces (#3533 / #3547).
///
/// The single endpoint accessor for the workspace list: a view observes
/// `workspaces` and dispatches the named actions below; the store owns fetching
/// (never a view calling `ChatService` directly). `chat = agent =
/// workspace` (#3540) — a chat is ephemeral until saved on-demand.
///
/// One instance per library (registered on `LibraryReference`), shared across
/// that library's windows.
@MainActor
@Observable
final class WorkspaceStore {
    // ─── Published domain state (views read these directly) ───
    private(set) var workspaces: [Components.Schemas.AgentWorkspace] = []
    private(set) var isLoading = false
    private(set) var loadError: String?

    // ─── Transport: the EXISTING generated chat service, unchanged ───
    private let chatService: ChatService
    private let log = Logger(subsystem: "app.fichero.fichero", category: "WorkspaceStore")

    init(chatService: ChatService) {
        self.chatService = chatService
    }

    /// Load the saved workspaces. Idempotent unless `force`.
    func load(force: Bool = false) async {
        if !force, !workspaces.isEmpty, loadError == nil { return }
        isLoading = true
        defer { isLoading = false }
        do {
            workspaces = try await chatService.listAgentWorkspaces()
            loadError = nil
        } catch {
            loadError = error.localizedDescription
            log.error("workspace list failed: \(error.localizedDescription)")
        }
    }

    /// Save a conversation as a workspace (on-demand), then refresh the list so
    /// the sidebar shows it. Returns the saved node, or nil on failure.
    @discardableResult
    func save(conversationId: String, title: String?) async -> Components.Schemas.AgentWorkspace? {
        do {
            let saved = try await chatService.saveConversationAsWorkspace(
                conversationId: conversationId,
                title: title
            )
            await load(force: true)
            return saved
        } catch {
            loadError = error.localizedDescription
            log.error("workspace save failed: \(error.localizedDescription)")
            return nil
        }
    }

    /// Fetch one workspace to restore its chat/agent session.
    func get(id: String) async -> Components.Schemas.AgentWorkspace? {
        try? await chatService.getAgentWorkspace(id: id)
    }

    /// Delete a workspace (reversible-safe per the backend), updating in place.
    func delete(id: String) async {
        do {
            try await chatService.deleteAgentWorkspace(id: id)
            workspaces.removeAll { $0.id == id }
        } catch {
            loadError = error.localizedDescription
            log.error("workspace delete failed: \(error.localizedDescription)")
        }
    }
}
