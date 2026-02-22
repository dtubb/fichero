import SwiftUI

/// Loading indicator for chat responses
struct ChatLoadingIndicator: View {
    var body: some View {
        HStack(spacing: 8) {
            ProgressView()
                .scaleEffect(0.8)
            Text("Searching and generating response...")
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .padding()
    }
}

/// Error view for chat errors
struct ChatErrorView: View {
    let message: String

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.triangle")
                .foregroundColor(.orange)
            Text(message)
                .font(.subheadline)
                .foregroundColor(.secondary)
        }
        .padding()
        .background(Color.orange.opacity(0.1))
        .cornerRadius(8)
    }
}

/// Empty state view for new conversations
struct ChatEmptyStateView: View {
    @Binding var inputText: String

    var body: some View {
        VStack(spacing: 16) {
            Image(systemName: "bubble.left.and.bubble.right")
                .font(.system(size: 48))
                .foregroundColor(.secondary)

            Text("Chat with your documents")
                .font(.headline)

            Text("Ask questions about your documents and get answers with source citations.")
                .font(.subheadline)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 300)

            VStack(alignment: .leading, spacing: 8) {
                Text("Try asking:")
                    .font(.caption)
                    .foregroundColor(.secondary)

                ForEach(sampleQuestions, id: \.self) { question in
                    Button {
                        inputText = question
                    } label: {
                        Text(question)
                            .font(.subheadline)
                            .foregroundColor(.accentColor)
                    }
                    .buttonStyle(.plain)
                }
            }
            .padding()
            .background(Color(.controlBackgroundColor))
            .cornerRadius(8)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private var sampleQuestions: [String] {
        [
            "What are the main themes in these documents?",
            "Summarize the key points from the letters",
            "Find mentions of specific people or places"
        ]
    }
}

/// Drop overlay for document drops
struct ChatDropOverlay: View {
    var body: some View {
        ZStack {
            Color.accentColor.opacity(0.1)
            VStack(spacing: 8) {
                Image(systemName: "plus.circle.fill")
                    .font(.largeTitle)
                    .foregroundColor(.accentColor)
                Text("Drop documents to add to chat scope")
                    .font(.headline)
                    .foregroundColor(.accentColor)
            }
        }
        .cornerRadius(12)
        .padding()
    }
}
