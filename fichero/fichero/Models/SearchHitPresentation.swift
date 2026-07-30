import FicheroAPIClient
import Foundation

/// How a non-document search hit is presented, and whether it can be opened
/// (#4403).
///
/// The engine searches four legs — documents, artifacts, entities, claims —
/// and returns all four typed. Only artifacts were ever rendered. Entities and
/// claims were consumed for `.count` alone, which is why searching a person who
/// demonstrably exists returned "Artifacts" and nothing else: the hit was
/// found, counted, and then had nowhere to go.
///
/// This maps each leg to the same row shape so one section view renders all
/// three, and so the mapping is testable without SwiftUI.
enum SearchHitPresentation {

    /// One rendered hit.
    struct Row: Equatable, Identifiable {
        /// Stable identity from the server's id where there is one.
        ///
        /// Never the array index: results re-rank between queries, and identity
        /// by position makes every row re-render and mis-animate. Where a hit
        /// carries no id the row falls back to a content-derived key, which is
        /// stable for the same result set.
        let id: String
        /// Short type tag shown in a capsule — "Person", "Claim", "transcription".
        let badge: String
        /// The line the user reads.
        let title: String
        /// Document to open when the row is activated, or `nil` when this hit
        /// has no document behind it. A `nil` here must disable the row and say
        /// why: a row that looks actionable and does nothing is worse than one
        /// that is visibly unavailable.
        let documentId: String?

        var isOpenable: Bool { documentId != nil }
    }

    /// How many rows a section shows before it has to be expanded.
    static let previewLimit = 5

    /// Why a row cannot be opened. Shown as help text on the disabled row —
    /// the affordance stays visible and explains itself.
    static let unopenableReason = "No source document recorded for this result"

    // MARK: - Entities

    /// Entity hits, in the order the engine ranked them.
    ///
    /// The opening document is the entity's first recorded source. Opening the
    /// ENTITY itself would be the better destination, but no window-level
    /// entity-navigation seam exists yet — see #4403.
    static func entityRows(_ hits: [Components.Schemas.SearchEntityHit]) -> [Row] {
        var rows: [Row] = []
        for (index, hit) in hits.enumerated() {
            let name = hit.canonicalName.trimmingCharacters(in: .whitespacesAndNewlines)
            rows.append(
                Row(
                    id: hit.id ?? "entity-\(index)-\(name)",
                    badge: entityBadge(hit),
                    title: name.isEmpty ? "Untitled entity" : name,
                    documentId: hit.sourceDocumentIds?.first
                )
            )
        }
        return rows
    }

    /// The entity's type, human-cased. Falls back to a neutral word rather than
    /// an empty capsule.
    static func entityBadge(_ hit: Components.Schemas.SearchEntityHit) -> String {
        guard let raw = hit.entityType?.rawValue, !raw.isEmpty else { return "Entity" }
        return raw.replacingOccurrences(of: "_", with: " ").capitalized
    }

    // MARK: - Claims

    /// Claim hits, in the order the engine ranked them.
    static func claimRows(_ hits: [Components.Schemas.SearchClaimHit]) -> [Row] {
        var rows: [Row] = []
        for (index, hit) in hits.enumerated() {
            let text = hit.text.trimmingCharacters(in: .whitespacesAndNewlines)
            rows.append(
                Row(
                    id: hit.id ?? "claim-\(index)",
                    badge: "Claim",
                    title: text.isEmpty ? "Empty claim" : singleLine(text),
                    documentId: hit.sourceDocumentId
                )
            )
        }
        return rows
    }

    // MARK: - Artifacts

    /// Artifact hits, in the order the engine ranked them.
    ///
    /// Folded onto the same row shape as the other two legs: the section that
    /// renders artifacts had the only working implementation, and copying it
    /// twice more would have carried its two defects (index identity, a dead
    /// overflow count) into the copies.
    static func artifactRows(_ hits: [Components.Schemas.SearchArtifactHit]) -> [Row] {
        var rows: [Row] = []
        for (index, hit) in hits.enumerated() {
            let snippet = (hit.snippet ?? hit.documentName ?? hit.documentId)
                .trimmingCharacters(in: .whitespacesAndNewlines)
            rows.append(
                Row(
                    id: "artifact-\(index)-\(hit.documentId)",
                    badge: hit.artifactType,
                    title: snippet.isEmpty ? hit.documentId : singleLine(snippet),
                    documentId: hit.documentId
                )
            )
        }
        return rows
    }

    // MARK: - Shared

    /// Collapse a multi-line snippet onto one line. A claim's text carries hard
    /// returns from the source document, and a row is one line tall.
    static func singleLine(_ text: String) -> String {
        text
            .split(whereSeparator: \.isNewline)
            .joined(separator: " ")
            .trimmingCharacters(in: .whitespaces)
    }
}
