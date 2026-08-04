import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// SSE consumer for `/api/activity/stream`.
///
/// This lives in Services because it drives the engine stream through the shared
/// `FicheroClient` transport (so it works over `.https` / `.uds` / in-process).
/// `ActivityStore` owns state only.
@MainActor
@Observable
final class ActivityStreamService {
    private let activityService: ActivityService
    @ObservationIgnored private let log = Logger(subsystem: "app.fichero.fichero", category: "ActivityStreamService")
    @ObservationIgnored nonisolated(unsafe) private var task: Task<Void, Never>?
    @ObservationIgnored private var started = false

    /// True once a connect/stream attempt has failed (or the server closed the
    /// stream) and activity events are NOT arriving — the UI shows a "live
    /// updates paused" pill instead of silently presenting a stale run list
    /// (#2518 no-silent-fallback, F7). Cleared on every successful (re)connect.
    private(set) var liveUpdatesUnavailable = false

    /// True after a 403 on connect — the caller has no role on this library.
    /// Retrying cannot mint authorization, so the run loop stops and the UI
    /// shows an access-denied state instead of a perpetual reconnect spinner
    /// (#2479). Cleared on `stop()` and on any successful (re)connect.
    private(set) var accessDenied = false

    /// The engine's OWN explanation for the 403, when it sent one (#4532).
    /// `nil` means it refused without a usable body. Never a guess: this is
    /// rendered to the user, and the previous hardcoded "no role on library"
    /// was wrong for the denial that actually occurs most often.
    private(set) var accessDeniedMessage: String?

    /// Distinguishes an authorization failure (terminal — don't retry) from a
    /// transient drop (retry with backoff).
    private enum StreamError: Error { case accessDenied(String?) }

    // nonisolated: pure failure-count logic with no main-actor state. Without this it
    // inherits @MainActor from the service and every #expect() assertion calling it from
    // a nonisolated test context fails to compile (#3902).
    nonisolated static func shouldSurfaceUnavailable(failureCount: Int) -> Bool {
        failureCount >= 2
    }

    /// Whether a transient drop should surface the paused pill. Only AFTER a
    /// successful connect — never during the initial connect window, where the
    /// app-level BackendConnectionView owns "not connected yet". Stops the pill
    /// flashing on launch (#3874). Once connected, the two-strike debounce applies.
    nonisolated static func shouldSurfaceAfterDrop(failureCount: Int, hasConnectedBefore: Bool) -> Bool {
        hasConnectedBefore && shouldSurfaceUnavailable(failureCount: failureCount)
    }

    init(activityService: ActivityService) {
        self.activityService = activityService
    }

    deinit {
        task?.cancel()
    }

    func start(onEvent: @escaping @MainActor (ActivityItem) -> Void) {
        guard !started else { return }
        started = true
        task = Task { [weak self] in
            await self?.runLoop(onEvent: onEvent)
        }
    }

    func stop() {
        task?.cancel()
        task = nil
        started = false
        liveUpdatesUnavailable = false  // intentional stop is not a paused stream
        accessDenied = false
    }

    private func runLoop(onEvent: @escaping @MainActor (ActivityItem) -> Void) async {
        var backoffNanos: UInt64 = 1_000_000_000
        var consecutiveUnavailableCycles = 0
        var hasConnectedBefore = false
        while !Task.isCancelled {
            do {
                try await subscribeOnce(onEvent: onEvent)
                hasConnectedBefore = true
                consecutiveUnavailableCycles = 0
                backoffNanos = 1_000_000_000
            } catch StreamError.accessDenied(let detail) {
                // 403: terminal (#2479). The cause is the engine's to state, not
                // ours to guess — see LibraryChangeStream for the same fix (#4532).
                if !Task.isCancelled {
                    let reason = detail ?? "engine gave no reason"
                    log.error("activity stream denied (403), not retrying — \(reason, privacy: .public)")
                    accessDeniedMessage = detail
                    accessDenied = true
                    liveUpdatesUnavailable = true
                }
                return
            } catch {
                if !Task.isCancelled {
                    log.error("activity stream dropped: \(error.localizedDescription, privacy: .public)")
                    consecutiveUnavailableCycles += 1
                    // Surface the pill only for a drop AFTER a successful connect;
                    // during the initial connect window the app-level
                    // BackendConnectionView owns "not connected yet", so the pill
                    // stays hidden and doesn't flash on launch (#3874).
                    liveUpdatesUnavailable = Self.shouldSurfaceAfterDrop(
                        failureCount: consecutiveUnavailableCycles,
                        hasConnectedBefore: hasConnectedBefore
                    )
                }
            }
            if Task.isCancelled { break }
            // A CLEAN end (subscribeOnce returned without throwing) is a healthy
            // server-side connection rotation, NOT a failure (#3351): the loop
            // reconnects next tick and `liveUpdatesUnavailable` was cleared on
            // connect. Counting it made a normal rotation + one transient error
            // surface the reconnect pill prematurely (spurious "Reconnect" while
            // healthy). Only genuine errors (the catch above) count.
            try? await Task.sleep(nanoseconds: backoffNanos)
            backoffNanos = min(backoffNanos * 2, 30_000_000_000)
        }
    }

    private func subscribeOnce(onEvent: @escaping @MainActor (ActivityItem) -> Void) async throws {
        // Route through the shared FicheroClient transport — auth and the
        // library-path header are applied by the client's middleware (nothing
        // hand-rolled). Works over `.https` / `.uds` / in-process.
        let (status, lines) = try await activityService.client.streamLines(
            pathComponents: ["activity", "stream"]
        )
        if status == 403 {
            // The engine's explanation is right here in `lines` (#4532).
            throw StreamError.accessDenied(await AccessError.denialMessage(fromBodyLines: lines))
        }
        guard status == 200 else {
            throw URLError(.badServerResponse)
        }
        accessDenied = false
        liveUpdatesUnavailable = false  // (re)connected — activity events flowing

        for try await line in lines {
            guard !Task.isCancelled else { break }
            if line.isEmpty || line.hasPrefix(":") || line.hasPrefix("event:") {
                continue
            }
            guard line.hasPrefix("data:") else { continue }
            let json = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
            if let activity = decodeActivity(json) {
                onEvent(activity)
            }
        }
    }

    private func decodeActivity(_ json: String) -> ActivityItem? {
        guard let data = json.data(using: .utf8) else { return nil }
        do {
            return try JSONDecoder().decode(ActivityItem.self, from: data)
        } catch {
            log.debug("activity stream undecodable frame: \(error.localizedDescription, privacy: .public)")
            return nil
        }
    }
}
