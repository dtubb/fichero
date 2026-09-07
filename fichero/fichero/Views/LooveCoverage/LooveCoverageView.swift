import SwiftUI

// MARK: - loove coverage window
//
// A dedicated window (scene id "loove-coverage" in FicheroApp) showing the
// tokenizer-language-coverage matrix: which models can actually READ which
// scripts. Rows are models, columns are languages. Each cell shows the coverage
// score (colored by band), a 4-segment tier bar (native/embedded/byte/unreachable),
// and the token tax (tokens per character).
//
// Self-contained: it owns its `LooveCoverageService`, which talks to the existing
// `/api/model-comparison/language-fit` engine route through the generated client.

struct LooveCoverageView: View {
    @State private var service = LooveCoverageService()

    /// The chosen language columns, persisted as a comma-separated list of codes
    /// so the selection survives closing and reopening the window.
    @AppStorage("loove.coverage.languages")
    private var selectedCodesRaw = LanguageCatalog.defaultSelectedCodes.joined(separator: ",")

    // Fixed column geometry so the header row and body rows align while the whole
    // matrix scrolls in both axes.
    private let modelColumnWidth: CGFloat = 220
    private let languageColumnWidth: CGFloat = 132

    /// The persisted selection as a set of codes.
    private var selectedCodes: Set<String> {
        Set(selectedCodesRaw.split(separator: ",").map(String.init))
    }

    /// The languages to fetch/show, in canonical catalog order.
    private var visibleLanguages: [CoverageLanguage] {
        LanguageCatalog.languages(for: selectedCodes)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            content
            Divider()
            creditFooter
        }
        .frame(minWidth: 640, minHeight: 480)
        .task {
            // Auto-load once on first open; the picker / Generate re-run it.
            if service.matrix == nil && !service.isLoading {
                await service.load(languages: visibleLanguages)
            }
        }
        // Re-fetch when the chosen language set changes — columns are added or
        // removed and the progressive fill runs for the new set.
        .onChange(of: selectedCodesRaw) {
            Task { await service.load(languages: visibleLanguages) }
        }
    }

    // MARK: Header + legend

    private var header: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .firstTextBaseline) {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Language Coverage")
                        .font(.title2.bold())
                    Text("How well each model's tokenizer can read each script — a measure of tokenizer coverage, not model intelligence or task quality.")
                        .font(.callout)
                        .foregroundStyle(.secondary)
                        .fixedSize(horizontal: false, vertical: true)
                }
                Spacer()
                languageMenu
                Button {
                    Task { await service.load(languages: visibleLanguages) }
                } label: {
                    Label(service.matrix == nil ? "Generate" : "Refresh", systemImage: "arrow.clockwise")
                }
                .disabled(service.isLoading)
            }

            legend
        }
        .padding(16)
    }

    /// Multi-select of which languages/scripts the matrix shows. Modern and
    /// historical are separate sections; toggling a row adds/removes that column
    /// and re-runs the fetch (via the persisted `selectedCodesRaw`).
    private var languageMenu: some View {
        Menu {
            Section("Modern") {
                ForEach(LanguageCatalog.modern) { language in
                    Toggle(language.name, isOn: languageBinding(for: language.code))
                }
            }
            Section("Historical") {
                ForEach(LanguageCatalog.historical) { language in
                    Toggle(language.name, isOn: languageBinding(for: language.code))
                }
            }
        } label: {
            Label("Languages (\(selectedCodes.count))", systemImage: "character.book.closed")
        }
        .disabled(service.isLoading)
    }

    /// A checkbox binding for one language code, writing the canonical
    /// catalog-ordered comma list back to `@AppStorage`.
    private func languageBinding(for code: String) -> Binding<Bool> {
        Binding(
            get: { selectedCodes.contains(code) },
            set: { isOn in
                var codes = selectedCodes
                if isOn { codes.insert(code) } else { codes.remove(code) }
                selectedCodesRaw = LanguageCatalog.all
                    .map(\.code)
                    .filter { codes.contains($0) }
                    .joined(separator: ",")
            }
        )
    }

    private var legend: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 14) {
                Text("Band")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                ForEach(CoverageBand.allCases, id: \.self) { band in
                    HStack(spacing: 4) {
                        Circle().fill(band.color).frame(width: 8, height: 8)
                        Text(band.label).font(.caption)
                    }
                }
            }
            HStack(spacing: 14) {
                Text("Tiers")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                ForEach(CoverageTier.allCases, id: \.self) { tier in
                    HStack(spacing: 4) {
                        RoundedRectangle(cornerRadius: 2)
                            .fill(tier.color)
                            .frame(width: 14, height: 8)
                        Text(tier.shortLabel).font(.caption)
                    }
                }
            }
            // The honesty key: what a number's rendering means.
            HStack(spacing: 14) {
                Text("Trust")
                    .font(.caption.bold())
                    .foregroundStyle(.secondary)
                HStack(spacing: 4) {
                    Text("0.86").font(.caption.monospacedDigit().weight(.semibold)).foregroundStyle(.green)
                    Text("measured (derived)").font(.caption)
                }
                HStack(spacing: 4) {
                    Text("~0.78").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    Text("estimate (heuristic)").font(.caption)
                }
                HStack(spacing: 4) {
                    Text("—").font(.caption.monospacedDigit()).foregroundStyle(.secondary)
                    Text("unknown").font(.caption)
                }
            }
        }
    }

    // MARK: Content states

    @ViewBuilder
    private var content: some View {
        if service.isLoading && (service.matrix?.isEmpty ?? true) {
            loadingState
        } else if let matrix = service.matrix, !matrix.isEmpty {
            matrixTable(matrix)
        } else {
            emptyState
        }
    }

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Scoring languages across configured models…")
                .font(.callout)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "character.book.closed")
                .font(.largeTitle)
                .foregroundStyle(.secondary)
            Text(service.errorMessage ?? "No coverage data yet.")
                .font(.callout)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 420)
            Button("Generate") {
                Task { await service.load(languages: visibleLanguages) }
            }
            .disabled(service.isLoading || visibleLanguages.isEmpty)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: Credit

    /// Attribution for the coverage method. loove is Andy Janco's work (MIT);
    /// credit it visibly, with the link.
    private var creditFooter: some View {
        HStack(spacing: 4) {
            Text("Coverage method:")
            Link("loove by Andy Janco", destination: URL(string: "https://github.com/apjanco/loove")!)
            Text("· MIT · Measures tokenizer/script fit, not model quality.")
        }
        .font(.caption2)
        .foregroundStyle(.secondary)
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    // MARK: Matrix

    private func matrixTable(_ matrix: CoverageMatrix) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            if hasHeuristic(matrix) {
                heuristicBanner
            }
            ScrollView([.horizontal, .vertical]) {
                VStack(alignment: .leading, spacing: 0) {
                    headerRow(matrix.languages)
                    Divider()
                    ForEach(matrix.rows) { row in
                        modelRow(row, languages: matrix.languages)
                        Divider()
                    }
                }
                .padding(.bottom, 8)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    /// True when any visible cell is a heuristic estimate — drives the banner so a
    /// viewer is told, up front, that some numbers are guesses.
    private func hasHeuristic(_ matrix: CoverageMatrix) -> Bool {
        matrix.rows.contains { row in
            row.cellsByLanguage.values.contains { $0.confidence == .heuristic }
        }
    }

    private var heuristicBanner: some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(
                "Scores marked ~ (est.) are heuristic per-script estimates — no derived "
                + "tokenizer coverage exists for that model yet. Only plain, band-colored "
                + "numbers are measured; “—” means unknown."
            )
                .font(.caption)
                .foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color.orange.opacity(0.08))
    }

    private func headerRow(_ languages: [CoverageLanguage]) -> some View {
        HStack(spacing: 0) {
            Text("Model")
                .font(.caption.bold())
                .foregroundStyle(.secondary)
                .frame(width: modelColumnWidth, alignment: .leading)
                .padding(.horizontal, 8)
            ForEach(languages) { language in
                let pending = service.pendingLanguages.contains(language.code)
                VStack(spacing: 1) {
                    Text(language.name).font(.caption.bold())
                    Text(language.code.uppercased())
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                // Dim a column header while its data is still computing, so the
                // eye follows the fill front as columns resolve.
                .opacity(pending ? 0.4 : 1)
                .frame(width: languageColumnWidth)
            }
        }
        .padding(.vertical, 6)
    }

    private func modelRow(_ row: CoverageModelRow, languages: [CoverageLanguage]) -> some View {
        HStack(spacing: 0) {
            VStack(alignment: .leading, spacing: 2) {
                Text(row.model)
                    .font(.callout)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text(row.provider)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .frame(width: modelColumnWidth, alignment: .leading)
            .padding(.horizontal, 8)

            ForEach(languages) { language in
                CoverageCellView(
                    cell: row.cellsByLanguage[language.code],
                    isPending: service.pendingLanguages.contains(language.code)
                )
                .frame(width: languageColumnWidth)
            }
        }
        .padding(.vertical, 6)
    }
}

// MARK: - Cell

private struct CoverageCellView: View {
    let cell: CoverageCell?
    /// This language's call is still in flight and no cell has landed yet — show
    /// "computing…" instead of a value or "—".
    var isPending: Bool = false

    private static let scoreFormat: FloatingPointFormatStyle<Double> =
        .number.precision(.fractionLength(2))

    private var confidence: CoverageConfidence { cell?.confidence ?? .unknown }
    private var isComputing: Bool { isPending && cell == nil }

    var body: some View {
        Group {
            if isComputing {
                computingCell
            } else {
                VStack(spacing: 4) {
                    scoreLine
                    // Colored tier bar ONLY for a real measurement; heuristic/unknown
                    // get a flat neutral track so the histogram can't read as data.
                    TierBar(counts: cell?.tierCounts, derived: confidence == .derived)
                    tokenTaxLine
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 2)
        .help(isComputing ? "Computing…" : tooltip)
    }

    /// Transient per-cell state while its column's request is in flight.
    private var computingCell: some View {
        VStack(spacing: 4) {
            ProgressView()
                .controlSize(.small)
            Text("computing…")
                .font(.caption2)
                .foregroundStyle(.secondary)
        }
    }

    /// The number itself, rendered by confidence:
    /// - derived → band-colored, bold (a measurement)
    /// - heuristic → "~N.NN" + "est.", muted secondary (a guess, never band color)
    /// - unknown → "—" + "unknown"
    @ViewBuilder
    private var scoreLine: some View {
        switch confidence {
        case .derived:
            Text(scoreText)
                .font(.body.monospacedDigit().weight(.semibold))
                .foregroundStyle(cell?.band.color ?? .secondary)
        case .heuristic:
            VStack(spacing: 0) {
                Text("~\(scoreText)")
                    .font(.body.monospacedDigit())
                    .foregroundStyle(.secondary)
                Text("est.")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        case .unknown:
            VStack(spacing: 0) {
                Text("—")
                    .font(.body.monospacedDigit())
                    .foregroundStyle(.secondary)
                Text("unknown")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }
        }
    }

    @ViewBuilder
    private var tokenTaxLine: some View {
        // Token tax is a real per-sample metric; show it only when the coverage
        // is measured. For a guess or unknown, suppress it (a muted placeholder)
        // so nothing on the cell reads as measured.
        if confidence == .derived, let tpc = cell?.tokensPerChar {
            Text("×\(tpc.formatted(Self.scoreFormat))/char")
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        } else {
            Text(" ")
                .font(.caption2.monospacedDigit())
        }
    }

    private var scoreText: String {
        guard let score = cell?.coverageScore else { return "—" }
        return score.formatted(Self.scoreFormat)
    }

    private var tooltip: String {
        guard let cell else { return "No data" }
        let trust: String
        switch cell.confidence {
        case .derived: trust = "Measured (derived tokenizer coverage)"
        case .heuristic: trust = "Estimate (heuristic per-script guess — not measured)"
        case .unknown: trust = "Unknown (no coverage data / no tokenizer)"
        }
        var parts = [trust, "band: \(cell.band.label)", "status: \(cell.status)", "source: \(cell.sourceKind)"]
        if let tpc = cell.tokensPerChar {
            parts.append("\(tpc.formatted(Self.scoreFormat)) tokens/char")
        }
        return parts.joined(separator: " · ")
    }
}

// MARK: - Tier bar

/// A 4-segment proportional bar of the LOOVE tier histogram. Colored segments
/// render ONLY for a derived measurement (`derived == true`); a heuristic /
/// unknown / empty cell gets a flat neutral track so a guess never shows a
/// measured-looking histogram, and the row height stays stable.
private struct TierBar: View {
    let counts: CoverageTierCounts?
    var derived: Bool = true

    private let barWidth: CGFloat = 96
    private let barHeight: CGFloat = 6

    var body: some View {
        if derived, let counts, !counts.isEmpty {
            HStack(spacing: 1) {
                ForEach(CoverageTier.allCases, id: \.self) { tier in
                    let width = segmentWidth(for: tier, total: counts.total, count: counts.count(for: tier))
                    if width > 0 {
                        Rectangle()
                            .fill(tier.color)
                            .frame(width: width, height: barHeight)
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 2))
            .frame(width: barWidth, height: barHeight)
        } else {
            RoundedRectangle(cornerRadius: 2)
                .fill(Color.secondary.opacity(0.15))
                .frame(width: barWidth, height: barHeight)
        }
    }

    private func segmentWidth(for tier: CoverageTier, total: Int, count: Int) -> CGFloat {
        guard total > 0 else { return 0 }
        return barWidth * CGFloat(count) / CGFloat(total)
    }
}

#if DEBUG
#Preview {
    LooveCoverageView()
}
#endif
