import SwiftUI

// MARK: - Mind Palace spatial view-models
//
// These mirror the backend `spatial_models.py` shapes (`SpatialNode`,
// `SpatialConnection`, `SpatialViewport`, `SpatialRoom`, `RoomSceneSummary`).
//
// We decode our own value types rather than the generated
// `Components.Schemas.SpatialNode` because the list endpoints
// (`/api/mind-palace/{rooms,nodes,connections}`) return the generic
// `MindPalaceListResponse` envelope whose `items` carry an *empty* item
// schema — swift-openapi-generator surfaces those as untyped
// `OpenAPIValueContainer` values, not typed nodes. `MindPalaceService`
// decodes each container into these models via a JSON round-trip using
// `.convertFromSnakeCase` (so `position_x` → `positionX`).
//
// Per `feedback_kg_logic_in_backend`: positions/arrangement are backend
// state. These models only carry what the backend provides — the views
// render at the backend-supplied coordinates and never compute layout.

/// Kind of item placed in a room. Maps `NodeType` (source/claim/note/
/// entity/transcription); decodes defensively to `.unknown` for any value
/// the backend adds later.
enum MindPalaceNodeType: String, Codable, CaseIterable {
    case source
    case claim
    case note
    case entity
    case transcription
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = MindPalaceNodeType(rawValue: raw) ?? .unknown
    }

    /// SF Symbol used to label a node by kind.
    var icon: String {
        switch self {
        case .source: return "doc.text"
        case .claim: return "quote.bubble"
        case .note: return "note.text"
        case .entity: return "person.crop.circle"
        case .transcription: return "text.quote"
        case .unknown: return "circle"
        }
    }

    /// Stable fill colour per kind, so a glance distinguishes node types.
    var color: Color {
        switch self {
        case .source: return .blue
        case .claim: return .purple
        case .note: return .orange
        case .entity: return .green
        case .transcription: return .teal
        case .unknown: return .gray
        }
    }

    var label: String {
        switch self {
        case .unknown: return "Unknown"
        default: return rawValue.capitalized
        }
    }
}

/// Typed link between two nodes. Maps `ConnectionType`
/// (evidentiary/semantic/ontological/hermeneutic/user_drawn).
enum MindPalaceConnectionType: String, Codable, CaseIterable {
    case evidentiary
    case semantic
    case ontological
    case hermeneutic
    case userDrawn = "user_drawn"
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = MindPalaceConnectionType(rawValue: raw) ?? .unknown
    }

    /// Edge colour per connection type.
    var color: Color {
        switch self {
        case .evidentiary: return .blue
        case .semantic: return .purple
        case .ontological: return .green
        case .hermeneutic: return .orange
        case .userDrawn: return .gray
        case .unknown: return .secondary
        }
    }
}

/// A spatial workspace room. Mirrors `SpatialRoom`.
struct MindPalaceRoom: Codable, Identifiable, Hashable {
    let id: String
    var name: String
    var description: String?
    var roomType: String?
    var ownerId: String?
}

/// A node placed in 3D space. Mirrors `SpatialNode`. Phase 1 renders the
/// 2D projection of `positionX`/`positionY`; `positionZ`, rotation, and
/// scale are carried for the deferred 3D view (B5) but unused for now.
struct MindPalaceNode: Codable, Identifiable, Hashable {
    let id: String
    let roomId: String
    let nodeType: MindPalaceNodeType
    var sourceId: String?
    var label: String
    var positionX: Double
    var positionY: Double
    var positionZ: Double
    var rotationX: Double
    var rotationY: Double
    var rotationZ: Double
    var scale: Double

    enum CodingKeys: String, CodingKey {
        case id, roomId, nodeType, sourceId, label
        case positionX, positionY, positionZ
        case rotationX, rotationY, rotationZ
        case scale
    }

    init(
        id: String = UUID().uuidString,
        roomId: String,
        nodeType: MindPalaceNodeType,
        sourceId: String? = nil,
        label: String,
        positionX: Double,
        positionY: Double,
        positionZ: Double = 0,
        rotationX: Double = 0,
        rotationY: Double = 0,
        rotationZ: Double = 0,
        scale: Double = 1
    ) {
        self.id = id
        self.roomId = roomId
        self.nodeType = nodeType
        self.sourceId = sourceId
        self.label = label
        self.positionX = positionX
        self.positionY = positionY
        self.positionZ = positionZ
        self.rotationX = rotationX
        self.rotationY = rotationY
        self.rotationZ = rotationZ
        self.scale = scale
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        // `id` is server-assigned; tolerate its (theoretical) absence so a
        // single malformed row can't drop the whole scene.
        id = (try? container.decode(String.self, forKey: .id)) ?? UUID().uuidString
        roomId = try container.decode(String.self, forKey: .roomId)
        nodeType = try container.decode(MindPalaceNodeType.self, forKey: .nodeType)
        sourceId = try? container.decode(String.self, forKey: .sourceId)
        label = (try? container.decode(String.self, forKey: .label)) ?? ""
        positionX = (try? container.decode(Double.self, forKey: .positionX)) ?? 0
        positionY = (try? container.decode(Double.self, forKey: .positionY)) ?? 0
        positionZ = (try? container.decode(Double.self, forKey: .positionZ)) ?? 0
        rotationX = (try? container.decode(Double.self, forKey: .rotationX)) ?? 0
        rotationY = (try? container.decode(Double.self, forKey: .rotationY)) ?? 0
        rotationZ = (try? container.decode(Double.self, forKey: .rotationZ)) ?? 0
        scale = (try? container.decode(Double.self, forKey: .scale)) ?? 1
    }

    /// Display label, falling back to the node kind when unlabeled.
    var displayLabel: String {
        label.isEmpty ? nodeType.label : label
    }

    func snappedPosition(gridSize: Double = 0.25) -> SIMD3<Double> {
        SIMD3<Double>(
            Self.snap(positionX, to: gridSize),
            Self.snap(positionY, to: gridSize),
            Self.snap(positionZ, to: gridSize)
        )
    }

    static func snap(_ value: Double, to gridSize: Double = 0.25) -> Double {
        guard gridSize > 0 else { return value }
        return (value / gridSize).rounded() * gridSize
    }

    /// Page-image URL used by the Mind Palace 3D view when a node has a
    /// source document. The backend schema doesn't currently declare a
    /// dedicated field, so this is a client-side wrapper over the storage
    /// thumbnail endpoint.
    var thumbnailUrl: URL? {
        guard let sourceId, !sourceId.isEmpty else { return nil }
        return Self.thumbnailURL(
            forSourceId: sourceId,
            baseURL: LibraryManager.shared.globalLibrary?.apiClient.baseURL
        )
    }

    static func thumbnailURL(
        forSourceId sourceId: String,
        baseURL: URL? = URL(string: "http://127.0.0.1:8765/api")
    ) -> URL? {
        guard !sourceId.isEmpty,
              let baseURL else { return nil }
        return baseURL.appendingPathComponent("storage/thumbnail/\(sourceId)")
    }
}

/// A visual link between nodes. Mirrors `SpatialConnection`.
struct MindPalaceConnection: Codable, Identifiable, Hashable {
    let id: String
    let roomId: String
    let sourceNodeId: String
    let targetNodeId: String
    let connectionType: MindPalaceConnectionType
    var linkSubtype: String?

    enum CodingKeys: String, CodingKey {
        case id, roomId, sourceNodeId, targetNodeId, connectionType, linkSubtype
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? container.decode(String.self, forKey: .id)) ?? UUID().uuidString
        roomId = try container.decode(String.self, forKey: .roomId)
        sourceNodeId = try container.decode(String.self, forKey: .sourceNodeId)
        targetNodeId = try container.decode(String.self, forKey: .targetNodeId)
        connectionType = try container.decode(MindPalaceConnectionType.self, forKey: .connectionType)
        linkSubtype = try? container.decode(String.self, forKey: .linkSubtype)
    }
}

/// A group/layer of nodes in a room. Mirrors `SpatialStack`.
struct MindPalaceStack: Codable, Identifiable, Hashable {
    let id: String
    let roomId: String
    var name: String?
    var nodeIds: [String]

    enum CodingKeys: String, CodingKey {
        case id, roomId, name, nodeIds
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        id = (try? container.decode(String.self, forKey: .id)) ?? UUID().uuidString
        roomId = try container.decode(String.self, forKey: .roomId)
        name = try? container.decode(String.self, forKey: .name)
        nodeIds = (try? container.decode([String].self, forKey: .nodeIds)) ?? []
    }
}

// MARK: - Phase 3: typed inter-content links (#1297 follow-up)

/// Reserved room ID for the "Whole Library" pseudo-room (Phase 3). When
/// `MindPalaceState.selectedRoomId` equals this, the container loads the
/// projection (`MindPalaceLibraryProjector`) instead of a real room's nodes.
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

/// Camera + focus state for a room. Mirrors `SpatialViewport`. Phase 1 reads
/// this to seed the canvas pan/zoom; B4 phase 2 will persist it back.
struct MindPalaceViewport: Codable, Hashable {
    var roomId: String
    var cameraX: Double
    var cameraY: Double
    var cameraZ: Double
    var zoomLevel: Double
    var focusNodeId: String?
    var bookmarkName: String?

    enum CodingKeys: String, CodingKey {
        case roomId, cameraX, cameraY, cameraZ, zoomLevel, focusNodeId, bookmarkName
    }

    init(from decoder: Decoder) throws {
        let container = try decoder.container(keyedBy: CodingKeys.self)
        roomId = try container.decode(String.self, forKey: .roomId)
        cameraX = (try? container.decode(Double.self, forKey: .cameraX)) ?? 0
        cameraY = (try? container.decode(Double.self, forKey: .cameraY)) ?? 0
        cameraZ = (try? container.decode(Double.self, forKey: .cameraZ)) ?? 10
        zoomLevel = (try? container.decode(Double.self, forKey: .zoomLevel)) ?? 1
        focusNodeId = try? container.decode(String.self, forKey: .focusNodeId)
        bookmarkName = try? container.decode(String.self, forKey: .bookmarkName)
    }
}
