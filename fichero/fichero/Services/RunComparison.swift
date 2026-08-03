import Foundation

// MARK: - Run comparison (#4341)
//
// Two runs of the same input, diffed where they disagree. Mirrors the
// server's `RunComparisonResponse`.
//
// The ordering of these fields is load-bearing. `comparable` must be read
// BEFORE `identical`: when a run did not complete there is nothing to
// compare, and reporting "identical" for two runs that both produced nothing
// would be the same lie as a green tick over an empty step.

/// One side of a comparison: which run, and what it did.
struct RunComparisonSide: Equatable {
    let threadId: String
    let workflowId: String
    let workflowName: String
    let status: String
    let error: String?
    let durationMs: Int?
    let artifactCount: Int
    let stepsTotal: Int
    let stepsFailed: Int
    let stepsNotRun: Int
    /// Steps that ran to completion and produced nothing — carried through
    /// from #4284 so the summary cannot present an empty run as a clean one.
    let stepsProducedNothing: Int
    let resolvedDocumentCount: Int?
}

/// A contiguous run of differing lines between the two transcriptions.
struct RunTextDifference: Identifiable, Equatable {
    let id = UUID()
    /// `changed`, `added` or `removed`.
    let kind: String
    let leftStartLine: Int?
    let rightStartLine: Int?
    let leftLines: [String]
    let rightLines: [String]
    let leftLineCount: Int
    let rightLineCount: Int
    /// The server clipped the quoted lines. Same rule as artifact previews:
    /// a clip that is not shown is a clip that misleads.
    let linesTruncated: Bool
}

/// Per-field set difference for structured artifacts (entities, and the like).
struct RunSetDifference: Identifiable, Equatable {
    let id = UUID()
    let fieldName: String
    let onlyLeft: [String]
    let onlyRight: [String]
    let sharedCount: Int
    /// True counts, which may exceed the labels actually listed.
    let onlyLeftCount: Int
    let onlyRightCount: Int
    let labelsTruncated: Bool
}

/// A scalar field that differs.
struct RunValueDifference: Identifiable, Equatable {
    let id = UUID()
    let fieldName: String
    let left: String?
    let right: String?
}

/// One artifact present on both sides, and how the two versions differ.
struct RunArtifactComparison: Identifiable, Equatable {
    let documentId: String
    let documentName: String?
    let artifactType: String
    let identical: Bool
    let leftProvenance: String?
    let rightProvenance: String?
    let textDifferences: [RunTextDifference]
    /// The server listed only the first N differing blocks. Without this the
    /// reader would take a partial list for the complete disagreement —
    /// the same failure mode as an unmarked truncated preview.
    let textDifferencesTruncated: Bool
    /// True total, which may exceed `textDifferences.count`.
    let textDifferenceCount: Int
    let setDifferences: [RunSetDifference]
    let valueDifferences: [RunValueDifference]

    var id: String { "\(documentId)-\(artifactType)" }
}

/// An artifact one side produced and the other did not.
struct RunComparisonOrphan: Identifiable, Equatable {
    let artifactId: String
    let documentId: String
    let documentName: String?
    let artifactType: String
    let stepName: String?
    let provenance: String?

    var id: String { artifactId }
}

/// The whole comparison.
struct RunComparison: Equatable {
    let left: RunComparisonSide
    let right: RunComparisonSide
    /// False when either run did not complete. Read this BEFORE `identical`.
    let comparable: Bool
    let incomparableReason: String?
    /// Whether both runs resolved to the same documents. Two runs over
    /// different inputs can differ for reasons that have nothing to do with
    /// the model, so this qualifies every difference below it.
    let sameInput: Bool?
    let inputNote: String
    /// nil whenever the comparison could not be made — never defaulted to
    /// false, which would read as "they differ".
    let identical: Bool?
    let differenceCount: Int
    let compared: [RunArtifactComparison]
    let onlyLeft: [RunComparisonOrphan]
    let onlyRight: [RunComparisonOrphan]
    /// The server's own words about what a fresh comparison costs. Shown
    /// verbatim rather than restated client-side, so the two cannot drift.
    let costNotice: String
}
