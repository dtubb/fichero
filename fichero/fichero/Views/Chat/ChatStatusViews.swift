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

/// Empty state for a new conversation: NOTHING (Daniel, 2026-08-23:
/// "everyone knows what a chat view is", and chat is not just documents —
/// it drives MCP tools and builds workflows, so no blurb narrows it).
struct ChatEmptyStateView: View {
    @Binding var inputText: String

    var body: some View {
        Color.clear
            .frame(maxWidth: .infinity, maxHeight: .infinity)
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
