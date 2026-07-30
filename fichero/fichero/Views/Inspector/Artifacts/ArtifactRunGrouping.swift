import Foundation

// MARK: - Provenance-first artifact grouping (#4319)

/// One section of the artifact browser: all artifacts produced by a single
/// workflow run, in pipeline order — or the trailing "Earlier" section that
/// collects legacy/ungrouped artifacts (no `runId`). Never hides anything:
/// every artifact lands in exactly one group.
struct ArtifactRunGroup: Identifiable, Equatable {
    /// The producing run (thread id), or `nil` for the "Earlier" section.
    let runId: String?
    /// The producing workflow id where known (for name lookup in headers).
    let workflowId: String?
    /// Newest artifact timestamp in the group — drives the header's relative
    /// time and the newest-first ordering of run groups.
    let latestCreatedAt: Date
    /// Artifacts in display order (pipeline `sequence` for runs).
    let artifacts: [Artifact]

    var id: String { runId ?? "earlier" }
    var isEarlier: Bool { runId == nil }
}

/// Pure grouping/ordering rules for the provenance-first artifact browser
/// (#4319), factored out of the view so they are unit-testable:
/// - artifacts group by `runId`; runs are ordered newest-first,
/// - within a run, rows follow pipeline `sequence` (legacy rows without a
///   sequence sort last, by creation date),
/// - artifacts with no `runId` collapse into a single trailing "Earlier"
///   group that keeps the old type-grouped reading order.
enum ArtifactRunGrouping {
    static func groups(from items: [Artifact]) -> [ArtifactRunGroup] {
        var byRun: [String: [Artifact]] = [:]
        var earlier: [Artifact] = []
        for artifact in items {
            if let runId = normalized(artifact.runId) {
                byRun[runId, default: []].append(artifact)
            } else {
                earlier.append(artifact)
            }
        }

        var groups: [ArtifactRunGroup] = byRun.map { runId, artifacts in
            let ordered = artifacts.sorted(by: pipelineOrder)
            return ArtifactRunGroup(
                runId: runId,
                workflowId: ordered.compactMap { normalized($0.workflowId) }.first,
                latestCreatedAt: artifacts.map(\.createdAt).max() ?? .distantPast,
                artifacts: ordered
            )
        }
        // Newest run first; id tiebreak keeps the order deterministic.
        groups.sort {
            if $0.latestCreatedAt != $1.latestCreatedAt {
                return $0.latestCreatedAt > $1.latestCreatedAt
            }
            return $0.id > $1.id
        }

        if !earlier.isEmpty {
            groups.append(
                ArtifactRunGroup(
                    runId: nil,
                    workflowId: nil,
                    latestCreatedAt: earlier.map(\.createdAt).max() ?? .distantPast,
                    artifacts: earlier.sorted(by: typeGroupedOrder)
                )
            )
        }
        return groups
    }

    /// Within a run: pipeline `sequence` ascending; legacy rows without a
    /// sequence sort after sequenced ones, oldest-first (creation order is the
    /// best remaining proxy for pipeline order); id as the final tiebreak.
    static func pipelineOrder(_ lhs: Artifact, _ rhs: Artifact) -> Bool {
        switch (lhs.sequence, rhs.sequence) {
        case let (lhsSeq?, rhsSeq?) where lhsSeq != rhsSeq:
            return lhsSeq < rhsSeq
        case (.some, .none):
            return true
        case (.none, .some):
            return false
        default:
            if lhs.createdAt != rhs.createdAt { return lhs.createdAt < rhs.createdAt }
            return lhs.id < rhs.id
        }
    }

    /// The pre-#4319 browse order, kept for the "Earlier" section: raw +
    /// cleaned pairs grouped by base type with the cleaned canonical entry
    /// first, then newest-first within a type.
    static func typeGroupedOrder(_ lhs: Artifact, _ rhs: Artifact) -> Bool {
        let lhsBase = baseType(of: lhs.artifactType)
        let rhsBase = baseType(of: rhs.artifactType)
        if lhsBase != rhsBase { return lhsBase < rhsBase }
        let lhsClean = lhs.artifactType.hasSuffix("_clean")
        let rhsClean = rhs.artifactType.hasSuffix("_clean")
        if lhsClean != rhsClean { return lhsClean }
        return lhs.createdAt > rhs.createdAt
    }

    static func baseType(of artifactType: String) -> String {
        artifactType.hasSuffix("_clean")
            ? String(artifactType.dropLast("_clean".count))
            : artifactType
    }

    private static func normalized(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
