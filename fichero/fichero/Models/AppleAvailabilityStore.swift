import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable store for the Apple Intelligence availability probe (#3121, #3118).
///
/// Wraps `GET /api/providers/apple/availability` so the UI learns *up front*
/// whether Apple Intelligence can run — and the concrete reason when it can't
/// (bridge missing / OS too old / Apple Intelligence off) — instead of failing
/// at first call. The only accessor of the endpoint; views read `status`.
@MainActor
@Observable
final class AppleAvailabilityStore {
    private(set) var status: AppleAvailability.Status?
    private(set) var isLoading = false

    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "AppleAvailabilityStore")

    init(client: FicheroClient) {
        self.client = client
    }

    /// Probe once (idempotent while in flight). Result is cached in `status`.
    func load() async {
        guard !isLoading else { return }
        isLoading = true
        defer { isLoading = false }
        do {
            let response = try await client.api
                .probeAppleIntelligenceApiProvidersAppleAvailabilityGet()
            if case .ok(let okResp) = response {
                let body = try okResp.body.json
                status = AppleAvailability.status(available: body.available, reason: body.reason)
            }
        } catch {
            // A cancelled/superseded probe is not an unavailability signal — keep
            // the prior status rather than marking Apple Intelligence unavailable.
            if error.isCancellationError { return }
            // A probe failure is itself an unavailable state — surface it, don't hide it.
            status = AppleAvailability.status(available: false, reason: error.localizedDescription)
            log.error("Apple availability probe failed: \(error.localizedDescription)")
        }
    }
}

// MARK: - Pure availability mapping (unit-tested; no client)

/// Presentation logic for Apple Intelligence availability, kept pure so the
/// available → row-state mapping is unit-testable without stubbing the probe.
enum AppleAvailability {
    struct Status: Equatable {
        let available: Bool
        /// Concrete reason shown verbatim when unavailable (never hidden).
        let reason: String?
        /// Short label for a status pill ("Available" / the reason).
        let label: String
    }

    static func status(available: Bool, reason: String?) -> Status {
        if available {
            return Status(available: true, reason: nil, label: "Available")
        }
        let detail = reason.flatMap { $0.isEmpty ? nil : $0 } ?? "Not available on this Mac"
        return Status(available: false, reason: detail, label: detail)
    }
}
