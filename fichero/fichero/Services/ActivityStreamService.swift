import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Raw SSE transport for `/api/activity/stream`.
///
/// This lives in Services because it builds the engine request and owns the
/// pinned URLSession. `ActivityStore` owns state only.
@MainActor
@Observable
final class ActivityStreamService {
    private let activityService: ActivityServiceGenerated
    @ObservationIgnored private let urlSession: URLSession = RemoteCertificatePinning.configuredSession()
    @ObservationIgnored private let log = Logger(subsystem: "app.fichero.fichero", category: "ActivityStreamService")
    @ObservationIgnored nonisolated(unsafe) private var task: Task<Void, Never>?
    @ObservationIgnored private var started = false

    /// True once a connect/stream attempt has failed (or the server closed the
    /// stream) and activity events are NOT arriving — the UI shows a "live
    /// updates paused" pill instead of silently presenting a stale run list
    /// (#2518 no-silent-fallback, F7). Cleared on every successful (re)connect.
    private(set) var liveUpdatesUnavailable = false

    init(activityService: ActivityServiceGenerated) {
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
    }

    private func runLoop(onEvent: @escaping @MainActor (ActivityItem) -> Void) async {
        var backoffNanos: UInt64 = 1_000_000_000
        while !Task.isCancelled {
            do {
                try await subscribeOnce(onEvent: onEvent)
                backoffNanos = 1_000_000_000
            } catch {
                if !Task.isCancelled {
                    log.error("activity stream dropped: \(error.localizedDescription, privacy: .public)")
                    liveUpdatesUnavailable = true
                }
            }
            if Task.isCancelled { break }
            // A clean close (no throw) also means events stopped until reconnect.
            liveUpdatesUnavailable = true
            try? await Task.sleep(nanoseconds: backoffNanos)
            backoffNanos = min(backoffNanos * 2, 30_000_000_000)
        }
    }

    private func subscribeOnce(onEvent: @escaping @MainActor (ActivityItem) -> Void) async throws {
        let request = engineEventStreamRequest(
            baseURL: activityService.client.apiBaseURL,
            pathComponents: ["activity", "stream"],
            libraryPath: activityService.client.currentLibraryPath
        )
        let (bytes, response) = try await urlSession.bytes(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        liveUpdatesUnavailable = false  // (re)connected — activity events flowing

        for try await line in bytes.lines {
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
