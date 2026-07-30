import FicheroAPIClient
import Observation
import SwiftUI

// MARK: - Models for the section's local rendering state

@MainActor
@Observable
final class KnowledgeGraphInspectorLoadState {
    var claims: [Components.Schemas.KnowledgeClaim] = []
    var canonicalGroups: [Components.Schemas.KGEntityGroup] = []
    var isLoading = false
    var loadError: String?
}

// MARK: - GroupedItem

struct GroupedItem: Identifiable {
    var entityId: String?
    let claimId: String
    let displayName: String
    let context: String
    let aliases: [String]
    let confidence: Double?
    /// First source page document id for this entity. Multiple sources are
    /// not surfaced yet — folder-cleanup merges retain the first claim's
    /// source, which is good enough for click-through provenance. (#833)
    /// Defaults to nil so existing #Preview fixtures and any non-claim
    /// callers compile without modification.
    var sourceDocumentId: String?
    /// Page label as recorded on the claim (e.g. "page 4", "folio 12r").
    /// Rendered as inline parenthetical when present.
    var sourcePageLabel: String?
    /// Verbatim quote the LLM lifted the claim from (#893). Shown as
    /// an italicised tappable citation underneath the curated context
    /// when distinct from both the displayName and the context. Tap
    /// runs a library search for the exact text — same path as the
    /// OntologyBrowser ClaimSummaryCard.
    var sourceExcerpt: String?
    /// Additional SVO claims for this same entity (#1109). When an entity
    /// has multiple substantive claims, the first lands in context/sourceExcerpt
    /// above; the rest accumulate here and render as secondary rows.
    struct ExtraClaim {
        let claimId: String
        let context: String
        let sourceDocumentId: String?
        let sourcePageLabel: String?
        let sourceExcerpt: String?
    }
    var extraClaims: [ExtraClaim] = []
    var includesChildren: Bool { !extraClaims.isEmpty }
    var id: String { claimId }

    init(
        entityId: String? = nil,
        claimId: String,
        displayName: String,
        context: String,
        aliases: [String],
        confidence: Double? = nil,
        sourceDocumentId: String? = nil,
        sourcePageLabel: String? = nil,
        sourceExcerpt: String? = nil,
        extraClaims: [ExtraClaim] = []
    ) {
        self.entityId = entityId
        self.claimId = claimId
        self.displayName = displayName
        self.context = context
        self.aliases = aliases
        self.confidence = confidence
        self.sourceDocumentId = sourceDocumentId
        self.sourcePageLabel = sourcePageLabel
        self.sourceExcerpt = sourceExcerpt
        self.extraClaims = extraClaims
    }
}
