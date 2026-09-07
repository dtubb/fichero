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

    /// Load coverage for an explicit language set, assembling the matrix.
    func load(languages: [CoverageLanguage]) async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        var rowsByModel: [String: CoverageModelRow] = [:]
        var modelOrder: [String] = []
        var failureCount = 0

        for language in languages {
            do {
                let response = try await client.api.getLanguageFitApiModelComparisonLanguageFitGet(
                    query: .init(language: language.code)
                )
                let payload = try response.ok.body.json
                for record in payload.results {
                    let cell = Self.cell(from: record)
                    if rowsByModel[cell.id] == nil {
                        rowsByModel[cell.id] = CoverageModelRow(
                            provider: cell.provider,
                            model: cell.model,
                            cellsByLanguage: [:]
                        )
                        modelOrder.append(cell.id)
                    }
                    rowsByModel[cell.id]?.cellsByLanguage[language.code] = cell
                }
            } catch {
                // A superseded call (view torn down / regenerate pressed again)
                // is not a failure — bail out quietly, matching ModelComparisonService.
                if error.isCancellationError { return }
                failureCount += 1
                logger.error("language-fit failed for \(language.code, privacy: .public): \(error.localizedDescription)")
            }
        }

        let rows = modelOrder
            .compactMap { rowsByModel[$0] }
            .sorted { ($0.provider, $0.model) < ($1.provider, $1.model) }

        matrix = CoverageMatrix(languages: languages, rows: rows)

        if rows.isEmpty {
            errorMessage = failureCount > 0
                ? "Couldn't load language coverage. Check that a model provider is configured and the engine is running."
                : "No models returned coverage data yet. Configure a provider in AI settings, then generate again."
        }
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
