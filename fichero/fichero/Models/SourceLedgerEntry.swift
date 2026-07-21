import Foundation

/// One entry in the unified **Source ledger** — the read-only provenance of what
/// a conversation actually *used* (see the consolidation fabel review, §3).
///
/// It unifies the three provenance shapes the surfaces grew independently:
/// `DocumentSource` (chat RAG), `ResearchSource` (a research project), and KG
/// usage. Distinct from the *pinned scope* (`ChatInspector` — what the user gave
/// the chat): pinned = input, ledger = what got cited. Honours "AI = instrument,
/// not interlocutor" — provenance the user can inspect, not narration.
///
/// KG usage is deliberately absent for now: `RetrievalInfo` carries only *counts*
/// (`kgClaimsUsed` / `kgEntitiesUsed`), not per-entity identities, so there is
/// nothing to link to. `.knowledge` exists for when identity-bearing KG usage
/// lands; the builder does not fabricate entries from counts.
struct SourceLedgerEntry: Identifiable, Hashable {
    let id: String
    var kind: Kind
    var label: String
    /// The node this came from (document id / research-source id), for linking.
    var nodeId: String?
    /// Excerpt (document) or URL (research source) — the scannable detail.
    var detail: String?

    enum Kind: String, Hashable {
        case document
        case research
        case knowledge

        var title: String {
            switch self {
            case .document: return "Documents"
            case .research: return "Research Sources"
            case .knowledge: return "Knowledge"
            }
        }

        var icon: String {
            switch self {
            case .document: return "doc.text"
            case .research: return "link"
            case .knowledge: return "point.3.connected.trianglepath.dotted"
            }
        }
    }
}

extension SourceLedgerEntry {
    init(from source: DocumentSource) {
        self.init(
            id: "document:\(source.documentId)",
            kind: .document,
            label: source.documentName,
            nodeId: source.documentId,
            detail: source.excerpt.isEmpty ? nil : source.excerpt
        )
    }

    init(from source: ResearchSource) {
        self.init(
            id: "research:\(source.id)",
            kind: .research,
            label: source.label,
            nodeId: source.id,
            detail: source.url ?? (source.description.isEmpty ? nil : source.description)
        )
    }

    /// Build the ledger for a conversation: every document cited across its
    /// messages (deduplicated by document — the same doc cited in three replies
    /// is one entry), plus any research-project sources. Stable order:
    /// documents in first-cited order, then research sources.
    static func ledger(
        for conversation: Conversation,
        researchSources: [ResearchSource] = []
    ) -> [SourceLedgerEntry] {
        var seen = Set<String>()
        var entries: [SourceLedgerEntry] = []

        for message in conversation.messages {
            for source in message.sources ?? [] {
                let entry = SourceLedgerEntry(from: source)
                if seen.insert(entry.id).inserted {
                    entries.append(entry)
                }
            }
        }
        for source in researchSources {
            let entry = SourceLedgerEntry(from: source)
            if seen.insert(entry.id).inserted {
                entries.append(entry)
            }
        }
        return entries
    }
}
