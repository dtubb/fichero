import FicheroAPIClient
import Foundation
import Observation
import OSLog

// MARK: - loove coverage service
//
// Fetches the tokenizer-language-coverage matrix by calling the ALREADY-EXISTING
// engine route `GET /api/model-comparison/language-fit` once per language, through
// the generated OpenAPI client (`FicheroClient` → auth + library middleware),
// mirroring `ModelComparisonService` (#1666/#1701). No hand-written URLSession
// layer, no engine/OpenAPI change.
//
// The endpoint, called with only a `language`, returns a `LanguageCoverageRecord`
// per configured model; we union the model keys across every language response so
// a model that scores for one script but not another still gets a row (its missing
// cells render "—").

@MainActor
@Observable
final class LooveCoverageService {
    private let logger = Logger(subsystem: "app.fichero.fichero", category: "LooveCoverageService")

    private(set) var isLoading = false
    private(set) var matrix: CoverageMatrix?
    private(set) var errorMessage: String?

    /// Language codes whose /language-fit call is still in flight. The view shows
    /// a "computing…" cell for these columns so the matrix visibly fills in as
    /// each call returns, rather than blocking on the slowest.
    private(set) var pendingLanguages: Set<String> = []

    /// Bumped per load; a column write from a superseded run (an older Generate)
    /// checks it and drops its result instead of clobbering the current matrix.
    private var loadGeneration = 0
    /// Languages whose call failed this run — distinguishes "all errored" from
    /// "nothing configured" in the empty-state message.
    private var failedThisRun: Set<String> = []

    /// Languages scored by the matrix — the engine's common set (English through
    /// Korean) covering Latin, Cyrillic, Greek, Arabic, Hebrew, Devanagari, and
    /// CJK scripts. Codes match the engine's language resolver.
    static let defaultLanguages: [CoverageLanguage] = [
        CoverageLanguage(code: "en", name: "English"),
        CoverageLanguage(code: "es", name: "Spanish"),
        CoverageLanguage(code: "ru", name: "Russian"),
        CoverageLanguage(code: "uk", name: "Ukrainian"),
        CoverageLanguage(code: "el", name: "Greek"),
        CoverageLanguage(code: "ar", name: "Arabic"),
        CoverageLanguage(code: "he", name: "Hebrew"),
        CoverageLanguage(code: "hi", name: "Hindi"),
        CoverageLanguage(code: "zh", name: "Chinese"),
        CoverageLanguage(code: "ja", name: "Japanese"),
        CoverageLanguage(code: "ko", name: "Korean")
    ]

    /// App-wide engine client (auth only, no library scope) — language fit is a
    /// dev-tier, app-wide diagnostic, exactly like model comparison. Mirrors
    /// `ModelComparisonService.client`.
    private let client: FicheroClient

    // See ModelComparisonService for why this is @ObservationIgnored +
    // nonisolated(unsafe): the @Observable macro otherwise wraps the stored
    // observer token and defeats the deinit read.
    @ObservationIgnored private nonisolated(unsafe) var hostChangeObservation: NSObjectProtocol?

    init() {
        self.client = FicheroClient(baseURL: EngineConfig.host, transportMode: EngineConfig.transportMode)
        hostChangeObservation = NotificationCenter.default.addObserver(
            forName: EngineConfig.engineHostDidChangeNotification,
            object: nil,
            queue: nil
        ) { [weak self] _ in
            Task { @MainActor in
                self?.client.reconfigure(baseURL: EngineConfig.host)
            }
        }
    }

    deinit {
        if let hostChangeObservation {
            NotificationCenter.default.removeObserver(hostChangeObservation)
        }
    }

    /// Load coverage for the default language set.
    func generate() async {
        await load(languages: Self.defaultLanguages)
    }

    /// Load coverage for an explicit language set, filling the matrix
    /// PROGRESSIVELY — each language's column appears as its call returns, so the
    /// user watches the matrix fill in rather than staring at one spinner until
    /// the slowest of 11 calls completes.
    ///
    /// One child task per language, each inheriting this @MainActor isolation, so
    /// its network `await` suspends off-main while the others proceed and every
    /// column write touches the observable state safely on the main actor.
    func load(languages: [CoverageLanguage]) async {
        loadGeneration += 1
        let generation = loadGeneration

        isLoading = true
        errorMessage = nil
        failedThisRun = []
        // Seed immediately: all columns known, no rows yet, everything pending —
        // the view can already draw the header + "computing…" columns.
        matrix = CoverageMatrix(languages: languages, rows: [])
        pendingLanguages = Set(languages.map(\.code))

        let tasks = languages.map { language in
            Task { @MainActor in
                await self.fetchColumn(language, generation: generation)
            }
        }
        for task in tasks {
            await task.value
        }

        // A newer Generate superseded us — it owns isLoading / the empty-state now.
        guard generation == loadGeneration else { return }

        isLoading = false
        if matrix?.rows.isEmpty ?? true {
            errorMessage = failedThisRun.isEmpty
                ? "No models returned coverage data yet. Configure a provider in AI settings, then generate again."
                : "Couldn't load language coverage. Check that a model provider is configured and the engine is running."
        }
    }

    /// Fetch one language's column and merge it into the matrix as soon as it
    /// arrives. Clears the column's pending flag on completion (success OR
    /// failure) so a failed column resolves to "unknown", never a stuck spinner.
    private func fetchColumn(_ language: CoverageLanguage, generation: Int) async {
        do {
            let response = try await client.api.getLanguageFitApiModelComparisonLanguageFitGet(
                query: .init(language: language.code)
            )
            let payload = try response.ok.body.json
            // A superseded run must not write into the current matrix.
            guard generation == loadGeneration else { return }
            merge(code: language.code, cells: payload.results.map { Self.cell(from: $0) })
        } catch {
            guard generation == loadGeneration else { return }
            // A superseded call cancels quietly; a real error marks the column
            // failed (it will render "unknown" once pending clears below).
            if !error.isCancellationError {
                failedThisRun.insert(language.code)
                logger.error("language-fit failed for \(language.code, privacy: .public): \(error.localizedDescription)")
            }
        }
        if generation == loadGeneration {
            pendingLanguages.remove(language.code)
        }
    }

    /// Merge one column's cells into the matrix, adding rows for any newly-seen
    /// model. Reassigns `matrix` (value type) so @Observable notifies the view;
    /// rows stay sorted so a late-arriving model pops into a stable position.
    private func merge(code: String, cells: [CoverageCell]) {
        guard var current = matrix else { return }
        var indexByModel = Dictionary(
            uniqueKeysWithValues: current.rows.enumerated().map { ($0.element.id, $0.offset) }
        )
        for cell in cells {
            if let idx = indexByModel[cell.id] {
                current.rows[idx].cellsByLanguage[code] = cell
            } else {
                current.rows.append(
                    CoverageModelRow(provider: cell.provider, model: cell.model, cellsByLanguage: [code: cell])
                )
                indexByModel[cell.id] = current.rows.count - 1
            }
        }
        current.rows.sort { ($0.provider, $0.model) < ($1.provider, $1.model) }
        matrix = current
    }

    /// Map one generated record onto the plain-Swift cell. Nil-safe throughout —
    /// a missing score / tier counts / fertility stays nil (rendered "—").
    private static func cell(
        from record: Components.Schemas.LanguageCoverageRecord
    ) -> CoverageCell {
        let tiers: CoverageTierCounts? = record.tierCounts.map { counts in
            CoverageTierCounts(
                native: counts.tier0Native ?? 0,
                embedded: counts.tier1Embedded ?? 0,
                byteFallback: counts.tier2ByteFallback ?? 0,
                unreachable: counts.tier3Unreachable ?? 0
            )
        }
        return CoverageCell(
            provider: record.provider,
            model: record.model,
            coverageScore: record.coverageScore,
            band: CoverageBand(rawBand: record.scoreBand?.rawValue),
            tierCounts: tiers,
            tokensPerChar: record.fertility?.tokensPerChar,
            status: record.status.rawValue,
            // `source.kind` is required on the record but its enum value is
            // optional; a missing kind means we have no idea where the number
            // came from, so treat it as "missing" (→ unknown in the UI).
            sourceKind: record.source.kind?.rawValue ?? "missing"
        )
    }
}
