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
                    Text(Self.cellText(error))
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

    /// What the cell says: the engine's first sentence AS SENT, for every error (`ai.where.dead-provider-says-why`, ## 950,
    /// ## 972). The app keeps no labels of its own ("No credits", "Rate limit" were guesses from substrings of the engine's
    /// prose, which a reword silently broke); the status carries the message only, with no error kind to switch on. The full
    /// message stays in the popover and the tooltip.
    nonisolated static func cellText(_ error: String) -> String {
        ActivityPopoverSummary.firstSentence(error)
    }
}
