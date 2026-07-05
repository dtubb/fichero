import SwiftUI

/// Chat pane scoped to a research project.
/// Re-uses the existing ChatView, filtering to conversations in /research/{project_id}.
struct ResearchChatPane: View {
    var project: ResearchProject
    @Environment(ConversationServiceGenerated.self) var conversationServiceGenerated
    @Environment(ChatServiceGenerated.self) var chatServiceGenerated

    @State private var chatSelectedDocuments: Set<String> = []

    var body: some View {
        ChatView(
            conversation: nil,
            selectedDocuments: $chatSelectedDocuments,
            onConversationUpdated: {}
        )
    }
}
