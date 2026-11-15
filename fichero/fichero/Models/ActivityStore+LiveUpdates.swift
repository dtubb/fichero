import Foundation

// The live-updates pill's state and its reconnect, split out of ActivityStore.swift (SwiftLint's size limits).

extension ActivityStore {
    /// True when the activity SSE stream has dropped and runs are no longer
    /// refreshing live (F7). Views show a "live updates paused" pill. Reads the
    /// nested @Observable stream service, so observers of this store re-render
    /// when it flips.
    var liveUpdatesPaused: Bool { streamService.liveUpdatesUnavailable }

    /// What Activity's pill says: "Reconnecting" only while the stream is retrying by itself; a refused stream does not
    /// retry, so it keeps the plain wording (#5912, review 601).
    var livePillMessage: String {
        liveUpdatesAccessDenied ? LiveUpdatesPausedPill.pausedMessage : LiveUpdatesPausedPill.reconnectingMessage
    }

    /// True when the activity stream was refused with a 403 — this device has no
    /// role on the library. A terminal state (no auto-retry): the UI shows an
    /// access-denied affordance rather than a reconnect spinner (#2479).
    var liveUpdatesAccessDenied: Bool { streamService.accessDenied }

    /// Force an immediate reconnect of the activity stream (the pill's action),
    /// rather than waiting out the backoff.
    func reconnectLiveUpdates() {
        stop()
        start()
    }
}
