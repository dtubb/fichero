import SwiftUI

/// Small capsule shown when an SSE stream has dropped and a surface is no longer
/// updating live (F7). It is the visible half of the no-silent-fallback rule
/// (#2518): rather than let a document list / run list / workflow quietly go
/// stale, the surface says so and offers a one-tap reconnect.
///
/// Reused by every live surface — wired to `LibraryChangeStream`,
/// `ActivityStreamService` (via `ActivityStore`), and `WorkflowStreamService`,
/// each of which exposes a `liveUpdatesUnavailable` flag. Render it in an
/// `.overlay(alignment: .top)` and gate it on that flag.
struct LiveUpdatesPausedPill: View {
    /// Force an immediate reconnect. Nil hides the button (the stream auto-retries
    /// with backoff regardless), leaving an informational pill.
    var onReconnect: (@MainActor () -> Void)?

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: "bolt.horizontal.circle")
                .foregroundStyle(.orange)
            Text("Live updates paused")
                .font(.callout)
            if let onReconnect {
                Button("Reconnect", action: onReconnect)
                    .buttonStyle(.borderless)
                    .font(.callout.weight(.medium))
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 6)
        .background(.thinMaterial, in: Capsule())
        .overlay(Capsule().strokeBorder(.separator))
        .shadow(radius: 2, y: 1)
        .padding(.top, 8)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Live updates paused")
        .accessibilityHint("The connection to the engine dropped; tap Reconnect to resume live updates.")
    }
}

#Preview("Informational") {
    LiveUpdatesPausedPill(onReconnect: nil)
        .padding()
}

#Preview("With reconnect") {
    LiveUpdatesPausedPill(onReconnect: {})
        .padding()
}
