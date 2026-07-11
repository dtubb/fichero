import FicheroAPIClient
import Foundation
import Observation
import OSLog

private let changeStreamLogger = Logger(
    subsystem: "app.fichero.fichero",
    category: "LibraryChangeStream"
)

// MARK: - ChangeEvent

/// A single data-layer change broadcast to a library's windows (#1863).
///
/// The Swift mirror of the backend `ChangeEvent`
/// (`api/change_stream.py`). `type` is `"{domain}.{verb}"` —
/// e.g. `entity.created`, `entity.updated`, `entity.deleted`, `entity.merged`,
/// `claim.updated`, `document.updated`. The id lists are domain-typed so a
/// document-scoped store can cheaply decide whether it cares.
struct ChangeEvent: Decodable, Sendable {
    let type: String
    let entityIds: [String]
    let claimIds: [String]
    let documentIds: [String]
    /// Citation rows touched (`citation.*`). The citation routes emit both
    /// `citation_ids` and the owning `document_ids`, so a document-scoped
    /// store filters on `documentIds` while a granular delete uses these.
    let citationIds: [String]
    /// Bibliography reference rows touched (`reference.*`). References are
    /// library-wide — `reference.*` carries only `reference_ids`, no
    /// `document_ids` — so a document-scoped bibliography store reloads its
    /// current scope on any reference event (the empty-`documentIds` path).
    let referenceIds: [String]
    let runId: String?
    let actor: String
    let originWindow: String?
    let timestamp: String?

    /// `"entity"` from `"entity.updated"`.
    var domain: String {
        type.split(separator: ".").first.map(String.init) ?? type
    }

    /// `"updated"` from `"entity.updated"` (`"merged"`, `"deleted"`, …).
    var verb: String {
        type.split(separator: ".").dropFirst().joined(separator: ".")
    }

    enum CodingKeys: String, CodingKey {
        case type
        case entityIds = "entity_ids"
        case claimIds = "claim_ids"
        case documentIds = "document_ids"
        case citationIds = "citation_ids"
        case referenceIds = "reference_ids"
        case runId = "run_id"
        case actor
        case originWindow = "origin_window"
        case timestamp = "ts"
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        type = try container.decode(String.self, forKey: .type)
        entityIds = try container.decodeIfPresent([String].self, forKey: .entityIds) ?? []
        claimIds = try container.decodeIfPresent([String].self, forKey: .claimIds) ?? []
        documentIds = try container.decodeIfPresent([String].self, forKey: .documentIds) ?? []
        citationIds = try container.decodeIfPresent([String].self, forKey: .citationIds) ?? []
        referenceIds = try container.decodeIfPresent([String].self, forKey: .referenceIds) ?? []
        runId = try container.decodeIfPresent(String.self, forKey: .runId)
        actor = try container.decodeIfPresent(String.self, forKey: .actor) ?? "system"
        originWindow = try container.decodeIfPresent(String.self, forKey: .originWindow)
        timestamp = try container.decodeIfPresent(String.self, forKey: .timestamp)
    }

    /// Reconstruct a change event from a `/api/activity/stream` frame that folds
    /// a mutation onto the activity stream for REMOTE subscribers (#3159 / #2479).
    /// The backend wraps each `ChangeEvent` as an activity response whose
    /// `metadata` carries `change_type` plus JSON-encoded id lists. Returns nil
    /// for an ordinary activity frame (no `change_type`), so the caller can tell
    /// a folded change apart from a real run/activity event.
    init?(activityMetadata metadata: [String: String]) {
        guard let changeType = metadata["change_type"], !changeType.isEmpty else { return nil }
        func ids(_ key: String) -> [String] {
            guard let raw = metadata[key],
                  let data = raw.data(using: .utf8),
                  let list = try? JSONDecoder().decode([String].self, from: data)
            else { return [] }
            return list
        }
        type = changeType
        entityIds = ids("entity_ids")
        claimIds = ids("claim_ids")
        documentIds = ids("document_ids")
        citationIds = ids("citation_ids")
        referenceIds = ids("reference_ids")
        runId = nil
        actor = metadata["actor"] ?? "system"
        // The folded activity frame carries no origin-window tag, so window-level
        // self-echo de-dup (route) is a no-op here; the store-level own-write
        // guard (#2478) still drops a device's echo of its own writes.
        originWindow = nil
        timestamp = metadata["ts"]
    }
}

// MARK: - ChangeEventConsumer

/// A domain store the change-stream fans events to (EntityStore, ClaimStore, …).
@MainActor
protocol ChangeEventConsumer: AnyObject {
    /// Event domains this consumer handles, e.g. `["entity"]`. The stream only
    /// delivers events whose `domain` is in this set.
    nonisolated var changeDomains: Set<String> { get }

    /// Apply one change event (already domain-filtered and self-echo-deduped).
    func apply(_ event: ChangeEvent)

    /// Re-fetch current scope after a reconnect — covers events missed while
    /// the SSE connection was down (spec §5.5, in-process queue has no replay).
    func resync() async
}

// MARK: - LibraryChangeStream

/// Per-library change-event SSE consumer (#1863). The generalization of
/// `WorkflowStreamService` from one workflow thread to one library: it owns the
/// `URLSession.bytes` loop on `GET /api/changes/stream`, decodes `data:` lines
/// into `ChangeEvent`, and fans each to the registered stores by domain.
///
/// One per library (registered on `LibraryReference`, shared across that
/// library's windows). Reconnects with backoff on drop and resyncs its stores
/// after each reconnect. `start()` is idempotent.
@MainActor
@Observable
final class LibraryChangeStream {
    private let baseURLProvider: @MainActor () -> URL
    private var baseURL: URL { baseURLProvider() }
    private let libraryPath: String

    /// This stream's origin tag — used for self-echo de-dup (spec §3.5) once
    /// optimistic local updates and the `X-Fichero-Origin-Window` header land.
    let windowId: String

    private struct WeakConsumer {
        weak var value: (any ChangeEventConsumer)?
    }
    private var consumers: [WeakConsumer] = []

    // Plumbing, not observed UI state — exclude from @Observable tracking, and
    // `nonisolated(unsafe)` so `deinit` (nonisolated in Swift 6) can cancel it
    // (only mutated on the main actor; `Task.cancel()` is safe from anywhere).
    @ObservationIgnored nonisolated(unsafe) private var task: Task<Void, Never>?
    private var started = false

    private(set) var isConnected = false

    /// True once a connect/stream attempt has failed and live updates are NOT
    /// arriving — the UI can surface a "live updates unavailable" affordance
    /// instead of silently showing stale data while the run completes server-side
    /// (#2518 — no-silent-fallback). Cleared on every successful (re)connect.
    /// Observed (not `@ObservationIgnored`) so views react to it.
    private(set) var liveUpdatesUnavailable = false

    /// The SSE transport (default: certificate-pinned `URLSession.bytes`). Held
    /// at the class level so its session outlives each `bytes(for:)` call — the
    /// delegate challenge handler only fires for a retained session. Injected in
    /// tests so canned frames can drive the classify loop without a socket.
    private let transport: any ChangeStreamTransport

    init(
        baseURL: URL,
        libraryPath: String,
        windowId: String = UUID().uuidString,
        transport: any ChangeStreamTransport =
            URLSessionChangeStreamTransport(session: RemoteCertificatePinning.configuredSession())
    ) {
        self.baseURLProvider = { baseURL }
        self.libraryPath = libraryPath
        self.windowId = windowId
        self.transport = transport
    }

    init(
        baseURLProvider: @escaping @MainActor () -> URL,
        libraryPath: String,
        windowId: String = UUID().uuidString,
        transport: any ChangeStreamTransport =
            URLSessionChangeStreamTransport(session: RemoteCertificatePinning.configuredSession())
    ) {
        self.baseURLProvider = baseURLProvider
        self.libraryPath = libraryPath
        self.windowId = windowId
        self.transport = transport
    }

    deinit {
        task?.cancel()
    }

    /// True after a 403 on connect — the caller has no role on this library.
    /// Retrying cannot mint authorization, so the run loop stops and the UI
    /// shows an access-denied state instead of a perpetual reconnect spinner
    /// (#2479). Cleared on `stop()`.
    private(set) var accessDenied = false

    /// Register a store to receive events for its `changeDomains`. Held weakly —
    /// the store's owner (`LibraryReference`) keeps it alive.
    func register(_ consumer: any ChangeEventConsumer) {
        consumers.append(WeakConsumer(value: consumer))
    }

    /// Fan a change event that arrived OUT OF BAND — reconstructed from the
    /// activity stream on a remote host (#3159 / #2479) — through the same
    /// domain-filtered, self-echo-deduped path as a native `/changes/stream`
    /// event, so remote and local change delivery share one apply path.
    func ingest(_ event: ChangeEvent) {
        route(event)
    }

    /// Open the SSE subscription (idempotent — safe to call from every window's
    /// `.task`; only the first call connects).
    func start() {
        guard !started else { return }
        started = true
        task = Task { [weak self] in
            await self?.runLoop()
        }
    }

    func stop() {
        task?.cancel()
        task = nil
        started = false
        isConnected = false
        accessDenied = false
    }

    // MARK: - Backoff (pure — unit-testable without timing)

    /// First reconnect delay, reset after every clean connect.
    static let initialBackoffNanos: UInt64 = 1_000_000_000  // 1s

    /// Next reconnect delay: double, capped at 30s.
    static func nextBackoffNanos(after current: UInt64) -> UInt64 {
        min(current * 2, 30_000_000_000)
    }

    static func shouldSurfaceUnavailable(failureCount: Int) -> Bool {
        failureCount >= 2
    }

    // MARK: - Internals

    /// Distinguishes an authorization failure (terminal — don't retry) from a
    /// transient drop (retry with backoff).
    private enum StreamError: Error { case accessDenied }

    private func runLoop() async {
        var backoffNanos = Self.initialBackoffNanos
        var hasConnectedBefore = false
        var consecutiveUnavailableCycles = 0
        while !Task.isCancelled {
            var cycleEndedWithError = false
            do {
                try await subscribeOnce(resyncOnConnect: hasConnectedBefore)
                hasConnectedBefore = true
                consecutiveUnavailableCycles = 0
                backoffNanos = Self.initialBackoffNanos  // clean end → reset backoff
            } catch StreamError.accessDenied {
                // 403: no role on this library. Retrying can't fix authorization —
                // flag it, surface access-denied, and stop the loop (#2479).
                if !Task.isCancelled {
                    changeStreamLogger.error("change-stream denied (403) — no role on library; not retrying")
                    accessDenied = true
                    liveUpdatesUnavailable = true
                }
                isConnected = false
                return
            } catch {
                if !Task.isCancelled {
                    cycleEndedWithError = true
                    // ponytail: require a second consecutive miss before surfacing
                    // the paused pill; one dropped cycle often self-heals on the
                    // next backoff tick and should stay invisible to the user.
                    changeStreamLogger.error(
                        "change-stream dropped: \(error.localizedDescription, privacy: .public)"
                    )
                    consecutiveUnavailableCycles += 1
                    liveUpdatesUnavailable = Self.shouldSurfaceUnavailable(
                        failureCount: consecutiveUnavailableCycles
                    )
                }
            }
            isConnected = false
            if !Task.isCancelled, !cycleEndedWithError {
                consecutiveUnavailableCycles += 1
                liveUpdatesUnavailable = Self.shouldSurfaceUnavailable(
                    failureCount: consecutiveUnavailableCycles
                )
            }
            if Task.isCancelled { break }
            try? await Task.sleep(nanoseconds: backoffNanos)
            backoffNanos = Self.nextBackoffNanos(after: backoffNanos)
        }
    }

    /// Open one SSE subscription and classify frames until it ends. `internal`
    /// (not `private`) so `@testable` tests can drive it directly with a stub
    /// transport, skipping the reconnect loop.
    func subscribeOnce(resyncOnConnect: Bool) async throws {
        let request = engineEventStreamRequest(
            baseURL: baseURL,
            pathComponents: ["changes", "stream"],
            libraryPath: libraryPath
        )

        let (status, lines) = try await transport.connect(request)
        if status == 403 {
            // 403: no role on this library — terminal, don't retry (#2479).
            throw StreamError.accessDenied
        }
        guard status == 200 else {
            throw URLError(.badServerResponse)
        }

        isConnected = true
        accessDenied = false
        liveUpdatesUnavailable = false  // (re)connected — live updates flowing (#2518)
        // On a *re*connect we may have missed events while down — resync stores.
        if resyncOnConnect {
            await resyncConsumers()
        }

        for try await line in lines {
            guard !Task.isCancelled else { break }
            if line.isEmpty || line.hasPrefix(":") || line.hasPrefix("event:") {
                continue  // keepalive comment / blank / event-type line
            }
            if line.hasPrefix("data:") {
                let json = String(line.dropFirst(5)).trimmingCharacters(in: .whitespaces)
                if let event = decode(json) {
                    route(event)
                }
            }
        }
    }

    private func decode(_ json: String) -> ChangeEvent? {
        guard let data = json.data(using: .utf8) else { return nil }
        do {
            return try JSONDecoder().decode(ChangeEvent.self, from: data)
        } catch {
            changeStreamLogger.debug(
                "change-stream undecodable frame: \(error.localizedDescription, privacy: .public)"
            )
            return nil
        }
    }

    private func route(_ event: ChangeEvent) {
        // Self-echo de-dup seam (spec §3.5): drop events this window initiated.
        if let origin = event.originWindow, origin == windowId { return }
        let domain = event.domain
        for box in consumers {
            guard let consumer = box.value else { continue }
            if consumer.changeDomains.contains(domain) {
                consumer.apply(event)
            }
        }
    }

    private func resyncConsumers() async {
        for box in consumers {
            await box.value?.resync()
        }
    }
}
