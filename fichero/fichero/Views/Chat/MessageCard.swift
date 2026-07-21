import SwiftUI

// MARK: - Message Bubble

/// Displays a single chat message in a bubble format — the one chat transcript
/// row (#1891 dropped the icon/table/map card variants in favour of this native
/// bubble layout).
struct MessageBubble: View {
    let message: ChatMessage

    var body: some View {
        VStack(alignment: message.role == .user ? .trailing : .leading, spacing: 8) {
            HStack {
                if message.role == .user { Spacer() }

                VStack(alignment: .leading, spacing: 8) {
                    MarkdownText(message.content)
                        .padding(12)
                        .background(bubbleBackground)
                        .foregroundColor(message.role == .user ? .white : .primary)
                        .cornerRadius(16)

                    // Retrieval step (search-as-a-tool) made visible.
                    if let retrieval = message.retrieval, retrieval.didSearch {
                        Label(retrieval.summary, systemImage: "magnifyingglass")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .padding(.leading, 12)
                    }

                    // Audited tool calls the agent made for this message (the
                    // ToolCall spine). Nil today; lights up when the engine wires
                    // the agentic /api/chat loop (migration step 2).
                    if let toolCalls = message.toolCalls, !toolCalls.isEmpty {
                        ForEach(toolCalls) { toolCall in
                            ToolCallCard(toolCall: toolCall)
                        }
                        .padding(.leading, 12)
                    }

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
