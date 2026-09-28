import Foundation

/// The Inspector's Links section (`build-notes-inspector.md` 5.7; `source.link.typed`,
/// `source.link.both-ways`, `source.segment.citable`, #5164): every typed link touching this segment,
/// read FROM THIS END -- "Is continued by Line 2" here, "Continues Line 1" there -- with how sure and
/// why. Verbs: link the two segments picked (first to second), withdraw a link, copy this segment's
/// reference. Pure: the words live where a test can reach them.
enum InspectorLinks {
    struct Link: Equatable, Identifiable {
        let id: String
        let linkType: String
        /// The sentence as it reads from this end (the engine turns it round for an inbound link).
        let label: String
        let otherKind: String
        let otherId: String
        let inbound: Bool
        var certainty: Double?
        var note: String?
    }

    struct LinkType: Equatable, Identifiable {
        let key: String
        let label: String
        var id: String { key }
    }

    struct Row: Equatable, Identifiable {
        let linkId: String
        /// "Is continued by".
        let sentence: String
        /// "Line · ܐܒܪܗܡ ܐܘܠܕ…", or what the other end is when it is not on this page.
        let other: String
        /// "sure 90% · the sentence runs on".
        let detail: String
        var id: String { linkId }
    }

    /// Each link in words. The other end is named from the page's own segments when it is one of them.
    static func rows(_ links: [Link], segments: [Segment]) -> [Row] {
        let byId = Dictionary(segments.map { ($0.id, $0) }, uniquingKeysWith: { first, _ in first })
        return links.map { link in
            var parts: [String] = []
            if let certainty = link.certainty { parts.append("sure \(Int((certainty * 100).rounded()))%") }
            if let note = link.note, !note.isEmpty { parts.append(note) }
            return Row(
                linkId: link.id, sentence: link.label, other: otherName(link, byId: byId),
                detail: parts.joined(separator: " · ")
            )
        }
    }

    private static func otherName(_ link: Link, byId: [String: Segment]) -> String {
        guard link.otherKind == "segment" else { return "a \(link.otherKind.replacingOccurrences(of: "_", with: " "))" }
        guard let other = byId[link.otherId] else { return "a segment on another page" }
        guard let text = other.text?.trimmingCharacters(in: .whitespaces), !text.isEmpty else {
            return other.kind.capitalized
        }
        let shown = text.count > 40 ? String(text.prefix(40)) + "…" : text
        return "\(other.kind.capitalized) · \(shown)"
    }

    /// The Link menu's two ends: exactly two segments picked, the first linked to the second.
    static func pair(_ selectedIds: [String]) -> (from: String, to: String)? {
        guard selectedIds.count == 2, selectedIds[0] != selectedIds[1] else { return nil }
        return (selectedIds[0], selectedIds[1])
    }
}

/// `typed_link.create`: `from` <type> `to`, both segments.
struct TypedLinkCreateRequest: Encodable, Equatable {
    let fromId: String
    let toId: String
    let linkType: String

    enum CodingKeys: String, CodingKey {
        case fromId = "from_id", toId = "to_id", linkType = "link_type"
    }
}

/// `typed_link.delete`: withdraw one link (soft; ⌘Z restores it).
struct TypedLinkIdRequest: Encodable, Equatable {
    let linkId: String

    enum CodingKeys: String, CodingKey { case linkId = "link_id" }
}
