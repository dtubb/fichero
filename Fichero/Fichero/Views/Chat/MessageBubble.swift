import SwiftUI

// MARK: - Message Bubble

/// Displays a single chat message in a bubble format
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
    VStack(spacing: 16) {
        MessageBubble(message: ChatMessage(
            role: .user,
            content: "Hello, can you help me?"
        ))

        MessageBubble(message: ChatMessage(
            role: .assistant,
            content: "Of course! I'd be happy to help you with your documents.",
            sources: [
                DocumentSource(documentId: "1", documentName: "Sample.pdf", relevanceScore: 0.95)
            ]
        ))
    }
    .padding()
    .frame(width: 400)
}
