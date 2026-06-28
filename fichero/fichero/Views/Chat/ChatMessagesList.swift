import SwiftUI

/// The chat transcript: native bubble layout, scrolled to the latest message.
///
/// Chat used to switch its transcript across the universal icon/table/map view
/// modes (#1891) — a non-standard oddity for a conversation. The transcript now
/// always renders as the native bubble list; the toolbar view modes stay where
/// they belong, on the library/search content.
struct ChatMessagesList: View {
    let conversation: Conversation
    let isLoading: Bool
    let errorMessage: String?
    @Binding var inputText: String

    var body: some View {
        if conversation.messages.isEmpty {
            ChatEmptyStateView(inputText: $inputText)
        } else {
            transcript
        }
    }

    private var transcript: some View {
        ScrollViewReader { proxy in
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 16) {
                    ForEach(conversation.messages) { message in
                        MessageBubble(message: message)
                            .id(message.id)
                    }

                    if isLoading {
                        ChatLoadingIndicator()
                    }

                    if let error = errorMessage {
                        ChatErrorView(message: error)
                    }
                }
                .padding()
            }
            .onChange(of: conversation.messages.count) { _, _ in
                if let lastMessage = conversation.messages.last {
                    withAnimation {
                        proxy.scrollTo(lastMessage.id, anchor: .bottom)
                    }
                }
            }
        }
        .background(Color(.textBackgroundColor))
    }
}
