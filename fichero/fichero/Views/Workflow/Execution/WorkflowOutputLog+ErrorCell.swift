import SwiftUI

// MARK: - Error Status Cell

/// Clickable error cell that shows full error in a popover
struct ErrorStatusCell: View {
    let error: String?
    @State private var showingPopover = false

    var body: some View {
        Button {
            showingPopover.toggle()
        } label: {
            HStack(spacing: 2) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.red)
                    .font(.caption2)
                if let error = error {
                    Text(Self.simplifyError(error))
                        .font(.caption2)
                        .foregroundColor(.red)
                        .lineLimit(1)
                }
            }
        }
        .buttonStyle(.plain)
        .popover(isPresented: $showingPopover, arrowEdge: .bottom) {
            errorPopoverContent
        }
        .help(error ?? "Unknown error")
    }

    private var errorPopoverContent: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Image(systemName: "exclamationmark.triangle.fill")
                    .foregroundColor(.red)
                Text("Error Details")
                    .font(.headline)
                Spacer()
                Button {
                    showingPopover = false
                } label: {
                    Image(systemName: "xmark.circle.fill")
                        .foregroundColor(.secondary)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Close error details")
            }

            Divider()

            if let error = error {
                Text(error)
                    .font(.system(.body, design: .monospaced))
                    .textSelection(.enabled)
                    .frame(maxWidth: 400, alignment: .leading)
                    .fixedSize(horizontal: false, vertical: true)
            } else {
                Text("Unknown error")
                    .foregroundColor(.secondary)
            }

            HStack {
                Spacer()
                Button("Copy") {
                    if let error = error {
                        PlatformPasteboard.writeString(error)
                    }
                }
                .buttonStyle(.bordered)
            }
        }
        .padding()
        .frame(minWidth: 300, maxWidth: 450)
    }

    /// The words a dead provider's cause is told in (`ai.where.dead-provider-says-why`, ## 950): no credit, a refused key, a
    /// rate limit. The engine words them (naming the provider and the fix), so the cell shows them as sent, never a label of
    /// the app's own; these are the phrases that mark the three.
    static let deadProviderMarks = ["no credit left", "refused the api key", "asking us to slow down", "asked us to slow down"]

    /// Extract the key part of an error message for display. A dead provider's error is the engine's first sentence as sent.
    nonisolated static func simplifyError(_ error: String) -> String {
        if deadProviderMarks.contains(where: { error.lowercased().contains($0) }) {
            return ActivityPopoverSummary.firstSentence(error)
        }
        if error.contains("402") || error.lowercased().contains("insufficient credits") {
            return "No credits"
        }
        if error.contains("401") || error.lowercased().contains("unauthorized") {
            return "Auth error"
        }
        if error.contains("timeout") || error.contains("timed out") {
            return "Timeout"
        }
        if error.contains("429") || error.lowercased().contains("rate limit") {
            return "Rate limit"
        }
        if error.contains("500") || error.contains("internal server") {
            return "Server error"
        }
        if error.count > 15 {
            return String(error.prefix(12)) + "..."
        }
        return error
    }
}
