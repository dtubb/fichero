import SwiftUI

// MARK: - Spatial view-models
//
// These mirror the backend `spatial_models.py` shapes used by the canvas.
//
// We decode our own value types rather than the generated
// `Components.Schemas.SpatialNode` because the list endpoints return an
// untyped envelope — swift-openapi-generator surfaces items as untyped
// `OpenAPIValueContainer` values. Callers decode each container into these
// models via a JSON round-trip using `.convertFromSnakeCase`
// (so `position_x` → `positionX`).
//
// Per `feedback_kg_logic_in_backend`: positions/arrangement are backend
// state. These models only carry what the backend provides — the views
// render at the backend-supplied coordinates and never compute layout.

/// Kind of item placed in a room. Maps `NodeType` (source/claim/note/
/// entity/transcription); decodes defensively to `.unknown` for any value
/// the backend adds later.
enum SpatialNodeType: String, Codable, CaseIterable {
    case source
    case claim
    case note
    case entity
    case transcription
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = SpatialNodeType(rawValue: raw) ?? .unknown
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
enum SpatialConnectionType: String, Codable, CaseIterable {
    case evidentiary
    case semantic
    case ontological
    case hermeneutic
    case userDrawn = "user_drawn"
    case unknown

    init(from decoder: Decoder) throws {
        let raw = try decoder.singleValueContainer().decode(String.self)
        self = SpatialConnectionType(rawValue: raw) ?? .unknown
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

/// A node placed in 3D space. Mirrors `SpatialNode`. Phase 1 renders the
/// 2D projection of `positionX`/`positionY`; `positionZ`, rotation, and
/// scale are carried for the deferred 3D view (B5) but unused for now.
struct SpatialNode: Codable, Identifiable, Hashable {
    let id: String
    let roomId: String
    let nodeType: SpatialNodeType
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
        nodeType: SpatialNodeType,
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
        nodeType = try container.decode(SpatialNodeType.self, forKey: .nodeType)
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

    // The Spatial 3D view loads a node's page image through
    // `SpaceTextureCache` → `StorageService.thumbnailData(for:)` (the compliant,
    // transport-agnostic path). A former `thumbnailUrl`/`thumbnailURL(forSourceId:)`
    // pair that hand-built a raw `…/storage/thumbnail/<id>` engine URL was dead
    // (no consumers) and is removed — a raw engine URL would break under
    // UDS/in-memory transports. Any future URL-shaped consumer should use
    // `APIClient.storageResourceURL(.thumbnail, for:)` (`fichero-res://`).
}

/// A visual link between nodes. Mirrors `SpatialConnection`.
struct SpatialConnection: Codable, Identifiable, Hashable {
    let id: String
    let roomId: String
    let sourceNodeId: String
    let targetNodeId: String
    let connectionType: SpatialConnectionType
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
        connectionType = try container.decode(SpatialConnectionType.self, forKey: .connectionType)
        linkSubtype = try? container.decode(String.self, forKey: .linkSubtype)
    }
}

/// A group/layer of nodes in a room. Mirrors `SpatialStack`.
struct SpatialStack: Codable, Identifiable, Hashable {
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

/// Camera + focus state for a room. Mirrors `SpatialViewport`. Phase 1 reads
/// this to seed the canvas pan/zoom; B4 phase 2 will persist it back.
struct SpatialViewport: Codable, Hashable {
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
