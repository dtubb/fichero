import SwiftUI

// MARK: - Comparison rows (#4341)
//
// Split from RunComparisonView to keep both files inside the 400-line limit.

/// What a fresh comparison costs, in the server's own words.
///
/// Rendered as standing prose, never as a tooltip, a disclosure or a button
/// subtitle: a doubled spend the user discovers after clicking is exactly the
/// surprise this notice exists to prevent.
struct RunComparisonCostNotice: View {
    let text: String

    var body: some View {
        Label(text, systemImage: "dollarsign.circle")
            .font(.callout)
            .foregroundStyle(.secondary)
            .padding(10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(
                RoundedRectangle(cornerRadius: 8).fill(Color.orange.opacity(0.12))
            )
            .overlay(
                RoundedRectangle(cornerRadius: 8).stroke(Color.orange.opacity(0.35))
            )
            .accessibilityLabel("Cost of comparing: \(text)")
    }
}

/// The two runs side by side. Carries the #4284 step counts, so a run that
/// completed with half its steps producing nothing cannot present itself as
/// a clean run.
struct RunComparisonSidesView: View {
    let left: RunComparisonSide
    let right: RunComparisonSide

    var body: some View {
        Grid(alignment: .leading, horizontalSpacing: 16, verticalSpacing: 4) {
            GridRow {
                Text("").gridColumnAlignment(.leading)
                Text("First run").fontWeight(.semibold)
                Text("Second run").fontWeight(.semibold)
            }
            row("Status", left.status, right.status)
            row("Steps", left.stepsTotal.formatted(), right.stepsTotal.formatted())
            row("Failed", left.stepsFailed.formatted(), right.stepsFailed.formatted())
            row("Did not run", left.stepsNotRun.formatted(), right.stepsNotRun.formatted())
            row(
                "Produced nothing",
                left.stepsProducedNothing.formatted(),
                right.stepsProducedNothing.formatted()
            )
            row("Artifacts", left.artifactCount.formatted(), right.artifactCount.formatted())
        }
        .font(.caption)
        .monospacedDigit()
    }

    @ViewBuilder
    private func row(_ label: String, _ leftValue: String, _ rightValue: String) -> some View {
        GridRow {
            Text(label).foregroundStyle(.secondary)
            Text(leftValue)
            Text(rightValue)
        }
    }
}

/// One artifact present in both runs, and where the two versions disagree.
struct RunArtifactComparisonRow: View {
    let comparison: RunArtifactComparison

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack(spacing: 6) {
                Image(systemName: comparison.identical ? "equal.circle" : "arrow.left.arrow.right")
                    .foregroundStyle(comparison.identical ? .green : .blue)
                Text(comparison.documentName ?? comparison.documentId)
                    .fontWeight(.medium)
                    .lineLimit(1)
                    .truncationMode(.middle)
                Text(comparison.artifactType)
                    .foregroundStyle(.secondary)
            }
            .font(.callout)

            // Which model produced each side. Two runs differing is only
            // interesting once you know whether the model changed.
            if comparison.leftProvenance != nil || comparison.rightProvenance != nil {
                Text(
                    "\(comparison.leftProvenance ?? "model not recorded")  →  "
                        + "\(comparison.rightProvenance ?? "model not recorded")"
                )
                .font(.caption2)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
            }

            ForEach(comparison.textDifferences) { RunTextDifferenceRow(difference: $0) }

            if comparison.textDifferencesTruncated {
                Label(
                    "Showing \(comparison.textDifferences.count.formatted()) of "
                        + "\(comparison.textDifferenceCount.formatted()) differing passages",
                    systemImage: "scissors"
                )
                .font(.caption2)
                .foregroundStyle(.orange)
            }

            ForEach(comparison.setDifferences) { RunSetDifferenceRow(difference: $0) }

            ForEach(comparison.valueDifferences) { value in
                Text("\(value.fieldName): \(value.left ?? "—") → \(value.right ?? "—")")
                    .font(.caption)
                    .textSelection(.enabled)
            }
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8).fill(Color.secondary.opacity(0.08)))
    }
}

/// One contiguous disagreement, quoted from both sides.
struct RunTextDifferenceRow: View {
    let difference: RunTextDifference

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(headline)
                .font(.caption2)
                .foregroundStyle(.secondary)
            ForEach(Array(difference.leftLines.enumerated()), id: \.offset) { item in
                Text("− \(item.element)").foregroundStyle(.red)
            }
            ForEach(Array(difference.rightLines.enumerated()), id: \.offset) { item in
                Text("+ \(item.element)").foregroundStyle(.green)
            }
            if difference.linesTruncated {
                Label("Quoted lines clipped", systemImage: "scissors")
                    .font(.caption2)
                    .foregroundStyle(.orange)
            }
        }
        .font(.caption.monospaced())
        .textSelection(.enabled)
    }

    private var headline: String {
        if let line = difference.leftStartLine ?? difference.rightStartLine {
            return "\(difference.kind) at line \(line.formatted())"
        }
        return difference.kind
    }
}

/// Per-field set difference: what each side found that the other did not.
struct RunSetDifferenceRow: View {
    let difference: RunSetDifference

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(difference.fieldName)
                .font(.caption)
                .fontWeight(.medium)
            Text("\(difference.sharedCount.formatted()) shared")
                .font(.caption2)
                .foregroundStyle(.secondary)
            if !difference.onlyLeft.isEmpty {
                Text("Only first: \(difference.onlyLeft.joined(separator: ", "))")
                    .font(.caption2)
                    .foregroundStyle(.red)
            }
            if !difference.onlyRight.isEmpty {
                Text("Only second: \(difference.onlyRight.joined(separator: ", "))")
                    .font(.caption2)
                    .foregroundStyle(.green)
            }
            // The counts are the truth; the labels above may be a sample.
            if difference.labelsTruncated {
                Label(
                    "\(difference.onlyLeftCount.formatted()) / "
                        + "\(difference.onlyRightCount.formatted()) in total — labels clipped",
                    systemImage: "scissors"
                )
                .font(.caption2)
                .foregroundStyle(.orange)
            }
        }
        .textSelection(.enabled)
    }
}

/// Artifacts one run produced and the other did not.
struct RunComparisonOrphanList: View {
    let title: String
    let orphans: [RunComparisonOrphan]

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title)
                .font(.callout)
                .fontWeight(.medium)
            ForEach(orphans) { orphan in
                HStack(spacing: 6) {
                    Image(systemName: "sparkles").foregroundStyle(.secondary)
                    Text(orphan.documentName ?? orphan.documentId)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    Text(orphan.artifactType).foregroundStyle(.secondary)
                    if let provenance = orphan.provenance {
                        Text(provenance).foregroundStyle(.secondary)
                    }
                }
                .font(.caption)
            }
        }
    }
}
