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
                    Text(simplifyError(error))
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

    /// Extract the key part of an error message for display
    func simplifyError(_ error: String) -> String {
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
