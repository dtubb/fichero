import SwiftUI

/// Chat pane embedded in a research project workspace.
/// Today this reuses the library-wide ChatView unchanged; it does NOT yet scope
/// conversations to the project folder path (#3242).
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
