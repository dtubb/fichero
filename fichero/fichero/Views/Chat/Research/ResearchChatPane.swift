import SwiftUI

/// Chat pane embedded in a research project workspace.
///
/// Research keeps its 3-pane layout (chat | browser | tasks), but the
/// conversation component IS the one unified chat surface — this embeds the
/// shared `ChatView` (the SurfaceTabBar Conversation / Sources / Knowledge /
/// Compare surface from #3532 slices 1-2), never a separate chat
/// implementation. That completes the chat / research / agent unification
/// (#3532 / #3540: "just one chat interface… always an agent with MCP tools").
///
/// The only Research-specific bit is scoping: the saved-conversation shelf is
/// pinned to the project's folder path (`/research/{project_id}`), so each
/// workspace keeps its own threads without forking the surface (Research =
/// workspace, ties #3533).
struct ResearchChatPane: View {
    var project: ResearchProject
    @Environment(ConversationService.self) var conversationService
    @Environment(ChatService.self) var chatService

    @State private var chatSelectedDocuments: Set<String> = []

    static func conversationFolderPath(for project: ResearchProject) -> String {
        "/research/\(project.id)"
    }

    var body: some View {
        ChatView(
            conversation: nil,
            selectedDocuments: $chatSelectedDocuments,
            conversationFolderPath: Self.conversationFolderPath(for: project),
            researchProject: project,
            onConversationUpdated: {}
        )
    }
}
