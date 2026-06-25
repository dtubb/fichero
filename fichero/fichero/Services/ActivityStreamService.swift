import Foundation
import OSLog

/// Raw SSE transport for `/api/activity/stream`.
///
/// This lives in Services because it builds the engine request and owns the
/// pinned URLSession. `ActivityStore` owns state only.
@MainActor
final class ActivityStreamService {
    private let activityService: ActivityServiceGenerated
    private let urlSession: URLSession = RemoteCertificatePinning.configuredSession()
    private let log = Logger(subsystem: "app.fichero.fichero", category: "ActivityStreamService")
    nonisolated(unsafe) private var task: Task<Void, Never>?
    private var started = false

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
                }
            }
            if Task.isCancelled { break }
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
