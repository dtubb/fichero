import SwiftUI

/// Chat pane embedded in a research project workspace.
/// Reuses ChatView, but scopes its saved conversation list to the research
/// project's folder path (`/research/{project_id}`) so each workspace keeps
/// its own thread shelf without forking the chat surface.
struct ResearchChatPane: View {
    var project: ResearchProject
    @Environment(ConversationServiceGenerated.self) var conversationServiceGenerated
    @Environment(ChatServiceGenerated.self) var chatServiceGenerated

    @State private var chatSelectedDocuments: Set<String> = []

    static func conversationFolderPath(for project: ResearchProject) -> String {
        "/research/\(project.id)"
    }

    var body: some View {
        ChatView(
            conversation: nil,
            selectedDocuments: $chatSelectedDocuments,
            conversationFolderPath: Self.conversationFolderPath(for: project),
            onConversationUpdated: {}
        )
    }
}
