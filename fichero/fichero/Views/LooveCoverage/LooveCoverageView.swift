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

    // Fixed column geometry so the header row and body rows align while the whole
    // matrix scrolls in both axes.
    private let modelColumnWidth: CGFloat = 220
    private let languageColumnWidth: CGFloat = 132

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            content
        }
        .frame(minWidth: 640, minHeight: 480)
        .task {
            // Auto-load once on first open; the toolbar's Generate re-runs it.
            if service.matrix == nil && !service.isLoading {
                await service.generate()
            }
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
                Button {
                    Task { await service.generate() }
                } label: {
                    Label(service.matrix == nil ? "Generate" : "Refresh", systemImage: "arrow.clockwise")
                }
                .disabled(service.isLoading)
            }

            legend
        }
        .padding(16)
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
                Task { await service.generate() }
            }
            .disabled(service.isLoading)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: Matrix

    private func matrixTable(_ matrix: CoverageMatrix) -> some View {
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

    private func headerRow(_ languages: [CoverageLanguage]) -> some View {
        HStack(spacing: 0) {
            Text("Model")
                .font(.caption.bold())
                .foregroundStyle(.secondary)
                .frame(width: modelColumnWidth, alignment: .leading)
                .padding(.horizontal, 8)
            ForEach(languages) { language in
                VStack(spacing: 1) {
                    Text(language.name).font(.caption.bold())
                    Text(language.code.uppercased())
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
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
                CoverageCellView(cell: row.cellsByLanguage[language.code])
                    .frame(width: languageColumnWidth)
            }
        }
        .padding(.vertical, 6)
    }
}

// MARK: - Cell

private struct CoverageCellView: View {
    let cell: CoverageCell?

    private static let scoreFormat: FloatingPointFormatStyle<Double> =
        .number.precision(.fractionLength(2))

    var body: some View {
        VStack(spacing: 4) {
            if let cell, let score = cell.coverageScore {
                Text(score.formatted(Self.scoreFormat))
                    .font(.body.monospacedDigit().weight(.semibold))
                    .foregroundStyle(cell.band.color)
            } else {
                Text("—")
                    .font(.body.monospacedDigit())
                    .foregroundStyle(.secondary)
            }

            TierBar(counts: cell?.tierCounts)

            Text(tokenTaxText)
                .font(.caption2.monospacedDigit())
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 2)
        .help(tooltip)
    }

    private var tokenTaxText: String {
        guard let tpc = cell?.tokensPerChar else { return "—" }
        return "×\(tpc.formatted(.number.precision(.fractionLength(2))))/char"
    }

    private var tooltip: String {
        guard let cell else { return "No data" }
        var parts = ["\(cell.band.label) coverage", "status: \(cell.status)"]
        if let tpc = cell.tokensPerChar {
            parts.append("\(tpc.formatted(.number.precision(.fractionLength(2)))) tokens/char")
        }
        return parts.joined(separator: " · ")
    }
}

// MARK: - Tier bar

/// A 4-segment proportional bar of the LOOVE tier histogram. Empty / nil counts
/// render as a flat neutral track so the row height stays stable.
private struct TierBar: View {
    let counts: CoverageTierCounts?

    private let barWidth: CGFloat = 96
    private let barHeight: CGFloat = 6

    var body: some View {
        if let counts, !counts.isEmpty {
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
