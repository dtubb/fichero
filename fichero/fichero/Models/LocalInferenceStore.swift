import FicheroAPIClient
import Foundation
import Observation
import OSLog

/// Observable domain store for the MLX local-inference sidecar (#3120, EPIC #2615).
///
/// Surfaces the `/api/local-inference/*` spine (#3114–#3116/#3119) — MLX runtime
/// provisioning, the model catalog, and per-profile service status — through the
/// generated OpenAPI client. A view never calls the client directly: it reads
/// `runtime` / `catalog` / `serviceStatuses` / `downloads` and invokes the mutation
/// methods, which own all endpoint access (knowledge-consistency mandate).
///
/// One instance per app session, held on `AppState` (the sidecar is app-wide,
/// not library-scoped).
@MainActor
@Observable
final class LocalInferenceStore {
    private(set) var runtime: Components.Schemas.LocalInferenceRuntimeStatusResponse?
    private(set) var catalog: [Components.Schemas.LocalModelCatalogEntry] = []
    private(set) var profiles: [Components.Schemas.LocalProviderProfile] = []
    /// Per-profile live service status, keyed by profile id.
    private(set) var serviceStatuses: [String: Components.Schemas.LocalInferenceServiceStatus] = [:]
    /// In-flight (or last-seen) download jobs, keyed by model id — drives the
    /// per-row progress bar without re-rendering the whole list.
    private(set) var downloads: [String: Components.Schemas.LocalInferenceModelDownloadJobResponse] = [:]

    private(set) var isLoading = false
    private(set) var loadError: String?
    /// Set true while a runtime provision/remove is running (its progress is on `runtime.job`).
    private(set) var isRuntimeBusy = false

    private let client: FicheroClient
    private let log = Logger(subsystem: "app.fichero.fichero", category: "LocalInferenceStore")

    /// ponytail: naive 1s fixed-interval poll for job progress — MLX
    /// downloads/provisions are minute-scale, so backoff buys nothing.
    private let pollInterval: Duration = .seconds(1)

    init(client: FicheroClient) {
        self.client = client
    }

    // MARK: - Load

    func load() async {
        guard !isLoading else { return }
        isLoading = true
        loadError = nil
        defer { isLoading = false }

        async let runtimeTask = client.api.getLocalInferenceRuntimeStatusApiLocalInferenceRuntimeGet()
        async let catalogTask = client.api.listLocalInferenceCatalogApiLocalInferenceCatalogGet()
        async let profilesTask = client.api.listLocalInferenceProfilesApiLocalInferenceProfilesGet()

        do {
            if case .ok(let okResp) = try await runtimeTask { runtime = try okResp.body.json }
            if case .ok(let okResp) = try await catalogTask { catalog = try okResp.body.json.items }
            if case .ok(let okResp) = try await profilesTask { profiles = try okResp.body.json.items }
        } catch {
            loadError = error.localizedDescription
            log.error("Failed to load local inference state: \(error.localizedDescription)")
        }

        // Service status is per-profile; fetch for the managed, UI-visible ones.
        for profile in profiles where profile.managedByApp == true {
            await refreshStatus(profileId: profile.id)
        }
    }

    // MARK: - Runtime

    /// Provision the MLX runtime, then poll `/runtime` until the embedded job
    /// reaches a terminal state so the progress bar reflects the download.
    func provisionRuntime() async {
        isRuntimeBusy = true
        defer { isRuntimeBusy = false }
        do {
            if case .ok(let okResp) = try await client.api
                .provisionLocalInferenceRuntimeApiLocalInferenceRuntimeProvisionPost() {
                runtime = try okResp.body.json
            }
            await pollRuntimeUntilSettled()
        } catch {
            loadError = error.localizedDescription
            log.error("Runtime provision failed: \(error.localizedDescription)")
        }
    }

    func removeRuntime() async {
        isRuntimeBusy = true
        defer { isRuntimeBusy = false }
        do {
            _ = try await client.api.removeLocalInferenceRuntimeApiLocalInferenceRuntimeDelete()
            if case .ok(let okResp) = try await client.api
                .getLocalInferenceRuntimeStatusApiLocalInferenceRuntimeGet() {
                runtime = try okResp.body.json
            }
        } catch {
            loadError = error.localizedDescription
            log.error("Runtime remove failed: \(error.localizedDescription)")
        }
    }

    private func pollRuntimeUntilSettled() async {
        while !Task.isCancelled {
            guard let job = runtime?.job, !LocalInferenceDisplay.isTerminal(state: job.state, error: job.error, percent: job.percent) else {
                return
            }
            try? await Task.sleep(for: pollInterval)
            guard case .ok(let okResp)? = try? await client.api
                .getLocalInferenceRuntimeStatusApiLocalInferenceRuntimeGet() else { return }
            runtime = try? okResp.body.json
        }
    }

    // MARK: - Catalog / Downloads

    /// Start a model download and poll its job to terminal, streaming progress
    /// into `downloads[modelId]` (per-row update, no list re-render).
    func downloadModel(modelId: String) async {
        do {
            let response = try await client.api
                .downloadLocalInferenceModelApiLocalInferenceModelsModelIdDownloadPost(
                    path: .init(modelId: modelId)
                )
            guard case .ok(let okResp) = response else {
                loadError = "Download failed for \(modelId)"
                return
            }
            var job = try okResp.body.json
            downloads[modelId] = job

            while !Task.isCancelled,
                  !LocalInferenceDisplay.isTerminal(state: job.state, error: job.error, percent: job.percent) {
                try await Task.sleep(for: pollInterval)
                guard case .ok(let poll) = try await client.api
                    .getLocalInferenceModelDownloadApiLocalInferenceModelsDownloadsJobIdGet(
                        path: .init(jobId: job.jobId)
                    ) else { break }
                job = try poll.body.json
                downloads[modelId] = job
            }
            await refreshCatalog()
        } catch {
            loadError = error.localizedDescription
            log.error("Download failed for \(modelId): \(error.localizedDescription)")
        }
    }

    func cancelDownload(modelId: String) async {
        guard let jobId = downloads[modelId]?.jobId else { return }
        do {
            _ = try await client.api
                .cancelLocalInferenceModelDownloadApiLocalInferenceModelsDownloadsJobIdCancelPost(
                    path: .init(jobId: jobId)
                )
        } catch {
            log.error("Cancel download failed for \(modelId): \(error.localizedDescription)")
        }
    }

    func deleteModel(modelId: String) async {
        do {
            _ = try await client.api
                .deleteLocalInferenceModelApiLocalInferenceModelsModelIdDelete(
                    path: .init(modelId: modelId)
                )
            downloads[modelId] = nil
            await refreshCatalog()
        } catch {
            loadError = error.localizedDescription
            log.error("Delete failed for \(modelId): \(error.localizedDescription)")
        }
    }

    private func refreshCatalog() async {
        guard case .ok(let okResp)? = try? await client.api
            .listLocalInferenceCatalogApiLocalInferenceCatalogGet() else { return }
        catalog = (try? okResp.body.json.items) ?? catalog
    }

    // MARK: - Services

    func startProfile(id: String) async {
        do {
            let response = try await client.api
                .startLocalInferenceProfileApiLocalInferenceProfilesProfileIdStartPost(
                    path: .init(profileId: id)
                )
            if case .ok(let okResp) = response { serviceStatuses[id] = try okResp.body.json }
        } catch {
            loadError = error.localizedDescription
            log.error("Start profile \(id) failed: \(error.localizedDescription)")
        }
    }

    func stopProfile(id: String) async {
        do {
            let response = try await client.api
                .stopLocalInferenceProfileApiLocalInferenceProfilesProfileIdStopPost(
                    path: .init(profileId: id)
                )
            if case .ok(let okResp) = response { serviceStatuses[id] = try okResp.body.json }
        } catch {
            loadError = error.localizedDescription
            log.error("Stop profile \(id) failed: \(error.localizedDescription)")
        }
    }

    private func refreshStatus(profileId: String) async {
        guard case .ok(let okResp)? = try? await client.api
            .getLocalInferenceStatusApiLocalInferenceProfilesProfileIdStatusGet(
                path: .init(profileId: profileId)
            ) else { return }
        serviceStatuses[profileId] = try? okResp.body.json
    }
}

// MARK: - Pure display mapping (unit-tested; no client)

/// Presentation logic for local-inference UI, kept pure over primitives so the
/// state machine is unit-testable without stubbing the transport (#3120 tests).
enum LocalInferenceDisplay {
    enum Tint: Equatable {
        case neutral, active, warning, error, success
    }

    struct ServiceBadge: Equatable {
        let text: String
        let symbol: String
        let tint: Tint
    }

    /// Map a service `LocalServiceState` (+ optional last error) to a badge.
    /// `failed` surfaces the concrete error verbatim so a failure is never
    /// hidden behind a spinner (AI-integrity: facts, not reassurance).
    static func badge(state: String, lastError: String?) -> ServiceBadge {
        switch state {
        case "healthy":
            return ServiceBadge(text: "Healthy", symbol: "checkmark.circle.fill", tint: .success)
        case "starting":
            return ServiceBadge(text: "Starting…", symbol: "arrow.triangle.2.circlepath", tint: .active)
        case "degraded":
            return ServiceBadge(text: "Degraded", symbol: "exclamationmark.triangle.fill", tint: .warning)
        case "failed":
            let detail = lastError.flatMap { $0.isEmpty ? nil : $0 }
            return ServiceBadge(
                text: detail.map { "Failed — \($0)" } ?? "Failed",
                symbol: "xmark.octagon.fill",
                tint: .error
            )
        case "stopped":
            return ServiceBadge(text: "Stopped", symbol: "stop.circle", tint: .neutral)
        default:
            return ServiceBadge(text: state.capitalized, symbol: "circle", tint: .neutral)
        }
    }

    /// A job is done when it reports an error, hits 100%, or its free-text state
    /// reads as terminal. Used to stop the progress poll loop.
    static func isTerminal(state: String?, error: String?, percent: Double?) -> Bool {
        if let error, !error.isEmpty { return true }
        if let percent, percent >= 100 { return true }
        switch state?.lowercased() {
        case "completed", "complete", "done", "ready", "installed", "failed", "error", "cancelled", "canceled":
            return true
        default:
            return false
        }
    }

    struct CatalogRow: Equatable {
        let installed: Bool
        /// Greyed + non-actionable: the entry is unsupported on this machine.
        let disabled: Bool
        /// Shown verbatim when disabled (e.g. "requires 16 GB unified memory").
        let unsupportedReason: String?
    }

    /// Fold a catalog entry's flags into row state. An unsupported entry stays
    /// visible but greyed with its reason — a fact, never hidden (#3119).
    static func row(supported: Bool?, unsupportedReason: String?, installed: Bool?) -> CatalogRow {
        let isSupported = supported ?? true
        return CatalogRow(
            installed: installed ?? false,
            disabled: !isSupported,
            unsupportedReason: isSupported ? nil : unsupportedReason
        )
    }

    /// Download progress as 0...1, or nil when total is unknown (indeterminate bar).
    static func progressFraction(current: Int?, total: Int?, percent: Double?) -> Double? {
        if let percent { return min(max(percent / 100, 0), 1) }
        guard let current, let total, total > 0 else { return nil }
        return min(max(Double(current) / Double(total), 0), 1)
    }
}
