import SwiftUI

// MARK: - Message Card (for Icon view)

/// Card representation of a chat message for Icon/Grid view
struct MessageCard: View {
    let message: ChatMessage

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            // Role badge
            HStack {
                Image(systemName: message.role == .user ? "person.fill" : "brain.head.profile")
                    .foregroundColor(message.role == .user ? .accentColor : .purple)
                Text(message.role == .user ? "You" : "Assistant")
                    .font(.caption)
                    .fontWeight(.medium)
                Spacer()
            }

            // Content preview
            Text(message.content)
                .font(.subheadline)
                .foregroundColor(.primary)
                .lineLimit(4)

            // Retrieval step (search-as-a-tool) made visible.
            if let retrieval = message.retrieval, retrieval.didSearch {
                Label(retrieval.summary, systemImage: "magnifyingglass")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                    .lineLimit(1)
            }

            // Sources indicator
            if let sources = message.sources, !sources.isEmpty {
                HStack(spacing: 4) {
                    Image(systemName: "doc.text")
                        .font(.caption2)
                    Text("\(sources.count) source(s)")
                        .font(.caption2)
                }
                .foregroundColor(.secondary)
            }
        }
        .padding(12)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(message.role == .user ? Color.accentColor.opacity(0.1) : Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(Color(.separatorColor), lineWidth: 1)
        )
    }
}

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

                    // Retrieval step (search-as-a-tool) made visible.
                    if let retrieval = message.retrieval, retrieval.didSearch {
                        Label(retrieval.summary, systemImage: "magnifyingglass")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
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

// MARK: - Message Map Card (for Map view)

/// Card representation for spatial map view
struct MessageMapCard: View {
    let message: ChatMessage

    var body: some View {
        VStack(spacing: 6) {
            // Role icon
            Image(systemName: message.role == .user ? "person.fill" : "brain.head.profile")
                .font(.title2)
                .foregroundColor(message.role == .user ? .accentColor : .purple)
                .frame(width: 40, height: 40)
                .background((message.role == .user ? Color.accentColor : Color.purple).opacity(0.15))
                .clipShape(Circle())

            // Content preview
            Text(message.content)
                .font(.caption)
                .lineLimit(3)
                .multilineTextAlignment(.center)
                .frame(width: 140)

            // Retrieval + sources badges. Space is tight (160×130), so the
            // search step shows as a compact icon + label rather than the full
            // summary; the source count keeps its own badge.
            HStack(spacing: 4) {
                if let retrieval = message.retrieval, retrieval.didSearch {
                    Label("Searched", systemImage: "magnifyingglass")
                        .labelStyle(.iconOnly)
                        .font(.caption2)
                        .foregroundColor(.secondary)
                }
                if let sources = message.sources, !sources.isEmpty {
                    Text("\(sources.count) sources")
                        .font(.caption2)
                        .foregroundColor(.white)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.gray)
                        .clipShape(Capsule())
                }
            }
        }
        .padding(10)
        .frame(width: 160, height: 130)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 12))
        .overlay(
            RoundedRectangle(cornerRadius: 12)
                .stroke(message.role == .user ? Color.accentColor : Color.purple, lineWidth: 2)
        )
        .shadow(color: .black.opacity(0.1), radius: 2, x: 0, y: 1)
    }
}
