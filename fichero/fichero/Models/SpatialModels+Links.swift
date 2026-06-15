import SwiftUI

// MARK: - Phase 3: typed inter-content links (#1297 follow-up)

/// Reserved room ID for the "Whole Library" pseudo-room. When the selected
/// room is this sentinel, the view loads the library projection
/// (`MindPalaceLibraryProjector`) instead of a real room's nodes.
let wholeLibraryRoomId = "__library__"

/// Typed link between two content items (a document, page, entity, claim, or
/// note) — not between user-placed room nodes. `MindPalaceConnection` carries
/// the spatial-room edge a user drew; `LinkType` is the **semantic** kind of
/// the relation behind it.
///
/// Decodes leniently: any unrecognised raw value falls back to `.related` so a
/// new backend value can't drop the scene. Drawn from the backend's
/// `ClaimRelationType` plus the spatial-room `ConnectionType`.
enum LinkType: String, Codable, CaseIterable, Hashable {
    case citation
    case mentions
    case depicts
    case related
    case contradicts
    case supersedes
    case parentChild = "parent_child"
    case userDrawn = "user_drawn"
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = LinkType(rawValue: raw) ?? Self.fallback(for: raw)
    }

    /// Map a free-form predicate / subtype string onto the taxonomy.
    static func fallback(for raw: String) -> LinkType {
        switch raw.lowercased() {
        case "cites", "citation", "cited_by":
            return .citation
        case "mentions", "mentioned_in":
            return .mentions
        case "depicts", "pictured_in", "shown_in":
            return .depicts
        case "contradicts", "refutes":
            return .contradicts
        case "supersedes", "replaces":
            return .supersedes
        case "parent", "child", "parent_child", "contains":
            return .parentChild
        case "user_drawn", "manual":
            return .userDrawn
        default:
            return .related
        }
    }

    /// Stable display colour.
    var color: Color {
        switch self {
        case .citation: return .blue
        case .mentions: return .teal
        case .depicts: return .pink
        case .related: return .gray
        case .contradicts: return .red
        case .supersedes: return .orange
        case .parentChild: return .gray
        case .userDrawn: return .secondary
        case .unknown: return .secondary
        }
    }

    var isSolid: Bool {
        switch self {
        case .citation, .depicts, .parentChild, .contradicts, .supersedes:
            return true
        case .mentions, .related, .userDrawn, .unknown:
            return false
        }
    }
}

/// A typed link between two content items (document IDs or entity IDs).
/// Content-level edge the whole-library projection emits — distinct from
/// `MindPalaceConnection` (room-level).
struct MindPalaceLink: Hashable, Identifiable {
    let sourceId: String
    let targetId: String
    let linkType: LinkType
    var label: String?
    var weight: Double

    init(sourceId: String, targetId: String, linkType: LinkType, label: String? = nil, weight: Double = 1.0) {
        self.sourceId = sourceId
        self.targetId = targetId
        self.linkType = linkType
        self.label = label
        self.weight = weight
    }

    /// Stable composite ID — projection re-run dedups without comparing labels.
    var id: String { "\(sourceId)|\(targetId)|\(linkType.rawValue)" }
}

extension MindPalaceConnection {
    /// Best-effort `LinkType` for a room connection — reads `linkSubtype`
    /// first, then falls back to mapping the room-level `connectionType`.
    /// Lets the renderer paint room edges and content-level links with the
    /// same palette.
    var linkType: LinkType {
        if let subtype = linkSubtype, !subtype.isEmpty {
            return LinkType.fallback(for: subtype)
        }
        switch connectionType {
        case .evidentiary: return .citation
        case .semantic:    return .related
        case .ontological: return .parentChild
        case .hermeneutic: return .mentions
        case .userDrawn:   return .userDrawn
        case .unknown:     return .unknown
        }
    }
}
