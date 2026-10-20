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
    /// The default: a stream that is down (the WorkflowEditor's never reconnects; the Library's sits beside a manual
    /// Reconnect button).
    static let pausedMessage = "Live updates paused"
    /// Activity only, while its stream is really retrying by itself (#5912).
    static let reconnectingMessage = "Reconnecting to the engine…"
    static let reconnectNowTitle = "Reconnect now"

    /// Headline text. Defaults to the dropped-stream wording; an access-denied
    /// surface passes its own (#2479).
    var message: String = LiveUpdatesPausedPill.pausedMessage
    /// Leading SF Symbol. Defaults to the dropped-stream bolt.
    var systemImage: String = "bolt.horizontal.circle"
    /// Force an immediate reconnect. Nil hides the button (the stream auto-retries
    /// with backoff regardless), leaving an informational pill. A 403/access-denied
    /// surface leaves this nil — retrying can't mint authorization.
    var onReconnect: (@MainActor () -> Void)?
    /// The button's label; Activity says "Reconnect now" beside "Reconnecting…" (#5912).
    var reconnectTitle: String = ConnectionPresentation.Action.reconnect.title

    var body: some View {
        HStack(spacing: 8) {
            Image(systemName: systemImage)
                .foregroundStyle(.orange)
            Text(message)
                .font(.callout)
            if let onReconnect {
                // The SAME word the engine popover's primary action uses
                // (#4380): the pill and the popover must not offer the user two
                // differently-named ways to do one thing.
                Button(reconnectTitle, action: onReconnect)
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
        .accessibilityLabel(message)
        .accessibilityHint(onReconnect == nil
            ? "This device has no access to live updates for this project."
            : "The connection to the engine dropped; tap Reconnect to resume live updates.")
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
