import CoreGraphics
import FicheroAPIClient
import Foundation
import simd

// MARK: - Renderer-agnostic canvas scene description (#3103)

/// The canvas contract layer. Pure Swift, NO renderer: it turns the shared
/// `CanvasLayoutStore`/`CanvasItemStore` rows (#3082) into a renderer-agnostic
/// scene description, and both the ortho-2D and perspective-3D RealityKit
/// renderers are thin projections of it. Everything here is `Equatable` and
/// unit-tested; the stores are unchanged by this layer.
///
/// **Canonical coordinate space = backend/world space** — the space the 3D
/// renderer already persists (0.25 grid, y-up). The 2D renderer projects
/// `(x, −y)` and ignores z; the 3D renderer uses all three. One saved layout
/// row, two projections — this is what makes "move it in 2D, it moves in 3D".

/// What a placeable carries: a library node or a standalone canvas item.
enum CanvasContent: Equatable {
    case node(SpatialNode)
    case item(CanvasItemDisplay)

    /// The fields that change the RENDERED card (not position/size — those are
    /// their own diff ops). Drives `CanvasSceneDiff`'s `.updateContent`.
    var contentSignature: [String] {
        switch self {
        case .node(let node):
            return [node.displayLabel, node.nodeType.rawValue, node.sourceId ?? ""]
        case .item(let item):
            return [item.text ?? "", item.kind.rawValue, item.sourceItemId ?? "", item.targetItemId ?? ""]
        }
    }
}

/// One positioned thing in the scene, in canonical world space.
struct CanvasPlaceable: Identifiable, Equatable {
    let id: String
    let content: CanvasContent
    var position: SIMD3<Double>
    /// Persisted card size (from a layout row's `w`/`h`); nil → renderer default.
    var size: CGSize?
    var zIndex: Int
}

/// How an edge is painted — unifies room connections, typed content links, and
/// standalone `link` canvas items into ONE edge model (replacing the 2D
/// `edgeLayer` Path scan and the 3D `makeEdgeEntity` loops).
enum CanvasEdgeStyle: Equatable {
    case connection(LinkType)   // room connection or typed content link
    case userLink               // standalone user-drawn `link` canvas item
}

struct CanvasEdge: Identifiable, Equatable {
    let id: String
    let sourceId: String
    let targetId: String
    let style: CanvasEdgeStyle
}

/// The full renderer-agnostic scene at one instant.
struct CanvasSceneState: Equatable {
    var placeables: [CanvasPlaceable]
    var edges: [CanvasEdge]
    var selection: Set<String>

    static let empty = CanvasSceneState(placeables: [], edges: [], selection: [])
}

// MARK: - Position resolution — the ONE rule

extension CanvasSceneState {
    /// World-space spacing of the standalone-item cascade (a freshly-added note
    /// with no saved row lands here until dragged). Ported from the 3D
    /// `itemRawPositions` cascade so 2D and 3D agree on the fallback layout.
    static let itemCascadeSpacing = 0.6

    /// Resolve nodes + connections + links + items + saved rows into ONE scene's
    /// placeables + edges. Selection is controller-owned (`selectionSet`) and
    /// applied by the caller, so it stays out of position resolution.
    ///
    /// Position rule (unifying 2D `resolvedPositions` and 3D `effectivePosition`):
    ///   1. a saved `CanvasItemLayout` row wins → `(row.x, row.y, row.z)`;
    ///   2. no row, `.backendPosition` (3D) → a node's backend `(positionX/Y/Z)`,
    ///      a non-`link` item's deterministic 3-column cascade;
    ///   3. no row, `.grid` (2D, #4290) → the placeable's slot in a spaced grid.
    ///
    /// `defaultPlacement` defaults to `.backendPosition` so the 3D 'Space'
    /// renderer and every existing caller are unchanged. The 2D canvas passes
    /// `.grid` because the backend defaults live on the XZ plane, which the 2D
    /// projection flattens onto one line — see `CanvasDefaultPlacement`.
    ///
    /// Legacy note: pre-#3103 the 2D canvas persisted SCREEN-space pixels into
    /// these rows. Per the #3070 call we accept a one-time re-layout of old
    /// positions rather than a rescue heuristic — rows are read as world space.
    static func resolve(
        nodes: [SpatialNode],
        connections: [SpatialConnection],
        links: [SpatialLink],
        layoutRows: [CanvasItemLayout],
        items: [CanvasItemDisplay],
        defaultPlacement: CanvasDefaultPlacement = .backendPosition
    ) -> CanvasSceneState {
        let rowsById = Dictionary(layoutRows.map { ($0.itemId, $0) }, uniquingKeysWith: { _, latest in latest })

        var placeables: [CanvasPlaceable] = []
        placeables.reserveCapacity(nodes.count + items.count)

        // Grid slots are indexed over the WHOLE ordered board — nodes, then
        // non-link items — and a placeable keeps its slot whether or not it has
        // a row. Dragging one card therefore never reshuffles the others, which
        // is what makes the default layout feel like a place rather than a
        // reflow (#4290).
        var slot = 0

        // Nodes: saved row wins, else the chosen default.
        for node in nodes {
            let row = rowsById[node.id]
            let gridSlot = slot
            slot += 1
            let position = row.map { SIMD3<Double>($0.x, $0.y, $0.z) }
                ?? nodeDefaultPosition(node, slot: gridSlot, placement: defaultPlacement)
            placeables.append(
                CanvasPlaceable(
                    id: node.id,
                    content: .node(node),
                    position: position,
                    size: size(from: row),
                    zIndex: row?.zIndex ?? 0
                )
            )
        }

        // Non-link items: saved row wins, else the chosen default.
        var cascadeIndex = 0
        for item in items where item.kind != .link {
            let gridSlot = slot
            slot += 1
            let position: SIMD3<Double>
            if let row = rowsById[item.id] {
                position = SIMD3<Double>(row.x, row.y, row.z)
            } else {
                switch defaultPlacement {
                case .backendPosition:
                    position = cascadePosition(cascadeIndex)
                    cascadeIndex += 1
                case .grid(let columns):
                    position = CanvasGridPlacement.position(index: gridSlot, columns: columns)
                }
            }
            placeables.append(
                CanvasPlaceable(
                    id: item.id,
                    content: .item(item),
                    position: position,
                    size: size(from: rowsById[item.id]),
                    zIndex: rowsById[item.id]?.zIndex ?? 0
                )
            )
        }

        let edges = resolveEdges(connections: connections, links: links, items: items)
        return CanvasSceneState(placeables: placeables, edges: edges, selection: [])
    }

    /// Room connections + typed content links + standalone `link` items, unified
    /// into ONE edge list (replacing the 2D Path scan and the 3D edge loops).
    private static func resolveEdges(
        connections: [SpatialConnection],
        links: [SpatialLink],
        items: [CanvasItemDisplay]
    ) -> [CanvasEdge] {
        var edges: [CanvasEdge] = []
        for connection in connections {
            edges.append(
                CanvasEdge(
                    id: connection.id,
                    sourceId: connection.sourceNodeId,
                    targetId: connection.targetNodeId,
                    style: .connection(connection.linkType)
                )
            )
        }
        for link in links {
            edges.append(
                CanvasEdge(id: link.id, sourceId: link.sourceId, targetId: link.targetId, style: .connection(link.linkType))
            )
        }
        for item in items where item.kind == .link {
            guard let source = item.sourceItemId, let target = item.targetItemId else { continue }
            edges.append(CanvasEdge(id: item.id, sourceId: source, targetId: target, style: .userLink))
        }
        return edges
    }

    /// A row-less node's default position under `placement`. `.backendPosition`
    /// is the projector's own `(x, y, z)`; `.grid` ignores it, because those
    /// values are laid out on the XZ plane and the 2D projection drops z — which
    /// is precisely how a whole folder ended up on one line (#4290).
    private static func nodeDefaultPosition(
        _ node: SpatialNode, slot: Int, placement: CanvasDefaultPlacement
    ) -> SIMD3<Double> {
        switch placement {
        case .backendPosition:
            return SIMD3<Double>(node.positionX, node.positionY, node.positionZ)
        case .grid(let columns):
            return CanvasGridPlacement.position(index: slot, columns: columns)
        }
    }

    /// The cascade slot for the `index`-th row-less standalone item: a 3-column
    /// grid marching down in world space (y decreases → down when 2D flips y).
    static func cascadePosition(_ index: Int) -> SIMD3<Double> {
        let column = Double(index % 3)
        let line = Double(index / 3)
        return SIMD3<Double>(column * itemCascadeSpacing, -line * itemCascadeSpacing, 0)
    }

    /// A layout row's persisted card size, or nil when it carries no `w`/`h`.
    private static func size(from row: CanvasItemLayout?) -> CGSize? {
        guard let row, let width = row.w, let height = row.h else { return nil }
        return CGSize(width: width, height: height)
    }
}
