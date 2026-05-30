import SwiftUI
#if canImport(RealityKit)
import RealityKit
#endif

/// RealityKit 3D rendering of a Mind Palace room — the `.threeD` render mode,
/// and the forward path toward streaming the palace to Vision Pro.
///
/// Renders each `MindPalaceNode` as a page-card at its **backend-provided**
/// `positionX/Y/Z` (with `rotation_*` and `scale` applied) and draws
/// connections as thin links. When a node has a source thumbnail, the card is
/// textured with the actual page image; otherwise it falls back to the
/// coloured block. Positions are read from the backend and only normalized
/// into a bounded cube for the camera — relative geometry is never
/// recomputed (`feedback_kg_logic_in_backend`).
///
/// The scene is rebuilt when the room's data changes (the container keys this
/// view by a scene signature). Tap-to-select, orbit, and zoom are wired through
/// RealityKit gestures. When RealityKit is unavailable the view falls back to
/// the 2D canvas.
struct SpatialScene3D: View {
    let nodes: [MindPalaceNode]
    let connections: [MindPalaceConnection]
    /// Phase 3 (#1297 follow-up): content-level typed links (whole-library
    /// projection). Drawn with the same cylinder mesh as room `connections`,
    /// colored by `LinkType`. Empty by default — existing room scenes
    /// unaffected.
    var links: [MindPalaceLink] = []
    var initialViewport: MindPalaceViewport?
    var onNodePositionChanged: (String, SIMD3<Double>) -> Void = { _, _ in }
    var onNodeMoveEnded: (String, SIMD3<Double>) -> Void = { _, _ in }
    var onViewportChanged: (SIMD3<Double>, Double) -> Void = { _, _ in }
    @Binding var selectedNodeId: String?

    #if canImport(RealityKit)
    @State private var cameraDistance = 5.5
    @State private var orbitYaw = 0.0
    @State private var orbitPitch = 0.0
    @State private var dragStart = CGSize.zero
    @State private var magnificationStart = 1.0
    @State private var nodeDragOrigins: [String: SIMD3<Double>] = [:]
    #endif

    var body: some View {
        if nodes.isEmpty {
            ContentUnavailableView(
                "Empty Space",
                systemImage: "cube.transparent",
                description: Text("No source pages or spatial nodes are available in this scope yet.")
            )
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(Color(nsColor: .textBackgroundColor))
        } else {
        #if canImport(RealityKit)
        RealityView(
            make: { content in
                // Default virtual camera, pulled back to frame the normalized cube.
                let camera = PerspectiveCamera()
                camera.name = "spatial-camera"
                updateCamera(camera)
                content.add(camera)

                let root = buildScene()
                root.name = "spatial-root"
                content.add(root)
            },
            update: { content in
                if let camera = content.entities
                    .compactMap({ $0 as? PerspectiveCamera })
                    .first(where: { $0.name == "spatial-camera" }) {
                    updateCamera(camera)
                }
            }
        )
        .gesture(
            TapGesture()
                .targetedToAnyEntity()
                .onEnded { value in
                    let nodeId = value.entity.name
                    guard !nodeId.isEmpty else { return }
                    selectedNodeId = nodeId
                }
        )
        .simultaneousGesture(cameraDragGesture)
        .simultaneousGesture(cameraZoomGesture)
        .simultaneousGesture(nodeDragGesture)
        .onAppear {
            applyInitialViewportIfNeeded()
        }
        .onChange(of: initialViewport) { _, _ in
            applyInitialViewportIfNeeded()
        }
        .onChange(of: selectedNodeId) { _, newValue in
            focusCamera(onNodeId: newValue)
        }
        .background(MindPalaceTheme.canvasBackground)
        #else
        Spatial2DCanvas(nodes: nodes, connections: connections, selectedNodeId: $selectedNodeId)
        #endif
        }
    }

    #if canImport(RealityKit)
    private var cameraDragGesture: some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                guard nodeDragOrigins.isEmpty else { return }
                let deltaWidth = value.translation.width - dragStart.width
                let deltaHeight = value.translation.height - dragStart.height
                orbitYaw += Double(deltaWidth) * 0.008
                orbitPitch = min(1.15, max(-1.15, orbitPitch + Double(deltaHeight) * 0.008))
                dragStart = value.translation
            }
            .onEnded { _ in
                dragStart = .zero
                persistViewport()
            }
    }

    private var cameraZoomGesture: some Gesture {
        MagnificationGesture()
            .onChanged { value in
                let delta = value / magnificationStart
                guard delta.isFinite, delta > 0 else { return }
                cameraDistance = min(12.0, max(2.2, cameraDistance / delta))
                magnificationStart = value
            }
            .onEnded { _ in
                magnificationStart = 1.0
                persistViewport()
            }
    }

    private var nodeDragGesture: some Gesture {
        DragGesture(minimumDistance: 2)
            .targetedToAnyEntity()
            .onChanged { value in
                let nodeId = value.entity.name
                guard let node = nodes.first(where: { $0.id == nodeId }) else { return }
                if nodeDragOrigins[nodeId] == nil {
                    nodeDragOrigins[nodeId] = SIMD3<Double>(node.positionX, node.positionY, node.positionZ)
                    selectedNodeId = nodeId
                }
                guard let origin = nodeDragOrigins[nodeId] else { return }
                let normalized = normalize()
                let rawDeltaX = Double(value.translation.width) * 0.01 / Double(normalized.scale)
                let rawDeltaY = -Double(value.translation.height) * 0.01 / Double(normalized.scale)
                let next = SIMD3<Double>(
                    MindPalaceNode.snap(origin.x + rawDeltaX),
                    MindPalaceNode.snap(origin.y + rawDeltaY),
                    origin.z
                )
                onNodePositionChanged(nodeId, next)
                let rawPosition = SIMD3<Float>(Float(next.x), Float(next.y), Float(next.z))
                value.entity.position = (rawPosition - normalized.center) * normalized.scale
            }
            .onEnded { value in
                let nodeId = value.entity.name
                if let node = nodes.first(where: { $0.id == nodeId }) {
                    let snapped = node.snappedPosition()
                    onNodeMoveEnded(nodeId, snapped)
                }
                nodeDragOrigins[nodeId] = nil
            }
    }

    private func updateCamera(_ camera: PerspectiveCamera) {
        let yaw = Float(orbitYaw)
        let pitch = Float(orbitPitch)
        let distance = Float(cameraDistance)
        let xPosition = sin(yaw) * cos(pitch) * distance
        let yPosition = sin(pitch) * distance
        let zPosition = cos(yaw) * cos(pitch) * distance
        camera.position = SIMD3<Float>(xPosition, yPosition, zPosition)
        camera.look(at: .zero, from: camera.position, relativeTo: nil)
    }

    private var currentCameraPosition: SIMD3<Double> {
        let yaw = orbitYaw
        let pitch = orbitPitch
        let distance = cameraDistance
        return SIMD3<Double>(
            sin(yaw) * cos(pitch) * distance,
            sin(pitch) * distance,
            cos(yaw) * cos(pitch) * distance
        )
    }

    private func persistViewport() {
        onViewportChanged(currentCameraPosition, cameraDistance)
    }

    /// Phase 3 follow-link behavior: on selection (tap), orbit camera toward
    /// the node and expose its first-degree neighbor set for future tinting.
    private func focusCamera(onNodeId nodeId: String?) {
        guard let nodeId, let node = nodes.first(where: { $0.id == nodeId }) else { return }
        let (scale, center) = normalize()
        let pos = position(for: node, scale: scale, center: center)
        let length = max(simd_length(SIMD3<Float>(pos.x, 0, pos.z)), 0.0001)
        let targetYaw = Double(atan2(pos.x, pos.z))
        let targetPitch = Double(atan2(pos.y, length))
        withAnimation(.easeInOut(duration: 0.45)) {
            orbitYaw = targetYaw
            orbitPitch = max(-1.15, min(1.15, targetPitch))
        }
        persistViewport()
    }

    /// First-degree neighbor IDs across both room connections and content
    /// links. Exposed (internal) so the inspector / future filter overlay can
    /// share the scan; renderer doesn't tint per-platform yet.
    func neighborIds(of nodeId: String) -> Set<String> {
        var result: Set<String> = []
        for connection in connections {
            if connection.sourceNodeId == nodeId { result.insert(connection.targetNodeId) }
            if connection.targetNodeId == nodeId { result.insert(connection.sourceNodeId) }
        }
        for link in links {
            if link.sourceId == nodeId { result.insert(link.targetId) }
            if link.targetId == nodeId { result.insert(link.sourceId) }
        }
        result.remove(nodeId)
        return result
    }

    private func applyInitialViewportIfNeeded() {
        guard let initialViewport else { return }
        let position = SIMD3<Double>(
            initialViewport.cameraX,
            initialViewport.cameraY,
            initialViewport.cameraZ
        )
        let distance = max(2.2, min(12.0, simd_length(position)))
        guard distance.isFinite, distance > 0 else { return }
        cameraDistance = distance
        orbitYaw = atan2(position.x, position.z)
        orbitPitch = asin(max(-1.0, min(1.0, position.y / distance)))
    }

    /// Normalize backend positions into a bounded cube (~[-1.5, 1.5]) so the
    /// fixed camera frames any room. Uniform scale preserves relative layout.
    private func normalize() -> (scale: Float, center: SIMD3<Float>) {
        guard !nodes.isEmpty else { return (1, .zero) }
        let xValues = nodes.map { Float($0.positionX) }
        let yValues = nodes.map { Float($0.positionY) }
        let zValues = nodes.map { Float($0.positionZ) }
        let center = SIMD3<Float>(
            (xValues.min()! + xValues.max()!) / 2,
            (yValues.min()! + yValues.max()!) / 2,
            (zValues.min()! + zValues.max()!) / 2
        )
        let span = max(
            xValues.max()! - xValues.min()!,
            yValues.max()! - yValues.min()!,
            zValues.max()! - zValues.min()!
        )
        let scale: Float = span > 0 ? 3.0 / span : 1
        return (scale, center)
    }

    private func position(for node: MindPalaceNode, scale: Float, center: SIMD3<Float>) -> SIMD3<Float> {
        let raw = SIMD3<Float>(Float(node.positionX), Float(node.positionY), Float(node.positionZ))
        return (raw - center) * scale
    }

    private func buildScene() -> Entity {
        let (scale, center) = normalize()
        let root = Entity()

        var positions: [String: SIMD3<Float>] = [:]
        for node in nodes {
            let pos = position(for: node, scale: scale, center: center)
            positions[node.id] = pos
            root.addChild(makeNodeEntity(node, at: pos))
        }

        // Room-level connections — typed by `linkType` (lenient mapping from
        // the room `ConnectionType` + optional `linkSubtype`).
        for connection in connections {
            guard
                let from = positions[connection.sourceNodeId],
                let toEnd = positions[connection.targetNodeId]
            else { continue }
            root.addChild(makeEdgeEntity(from: from, to: toEnd, linkType: connection.linkType, weight: 1.0))
        }

        // Phase 3: content-level typed links from the whole-library
        // projection. Same cylinder geometry, palette comes from `LinkType`.
        for link in links {
            guard
                let from = positions[link.sourceId],
                let toEnd = positions[link.targetId]
            else { continue }
            root.addChild(makeEdgeEntity(from: from, to: toEnd, linkType: link.linkType, weight: link.weight))
        }

        return root
    }

    private func makeNodeEntity(_ node: MindPalaceNode, at position: SIMD3<Float>) -> ModelEntity {
        let scale = Float(max(node.scale, 0.25))
        let cardWidth: Float = 0.8 * scale
        let cardHeight: Float = cardWidth / pageAspectRatio
        let thumbnailUrl = node.thumbnailUrl
        let nodeColor = MindPalaceTheme.materialColor(for: node.nodeType)
        let mesh: MeshResource
        let materials: [any RealityFoundation.Material]
        let collisionShape: ShapeResource

        switch node.nodeType {
        case .entity:
            // Phase 3: entity orbs (sphere). HoverEffectComponent gives the
            // per-platform highlight without #if.
            let radius: Float = cardWidth * 0.32
            mesh = MeshResource.generateSphere(radius: radius)
            materials = [SimpleMaterial(color: nodeColor, isMetallic: false)]
            collisionShape = ShapeResource.generateSphere(radius: radius)
        case .source where thumbnailUrl != nil, .source:
            mesh = MeshResource.generatePlane(
                width: cardWidth,
                height: cardHeight,
                cornerRadius: min(cardWidth, cardHeight) * 0.07
            )
            materials = [UnlitMaterial(color: nodeColor)]
            collisionShape = ShapeResource.generateBox(size: SIMD3<Float>(cardWidth, cardHeight, cardWidth * 0.12))
        default:
            let depth: Float = cardWidth * 0.12
            mesh = MeshResource.generateBox(
                size: SIMD3<Float>(cardWidth, cardHeight, depth),
                cornerRadius: min(cardWidth, cardHeight, depth) * 0.18
            )
            materials = [SimpleMaterial(color: nodeColor, isMetallic: false)]
            collisionShape = ShapeResource.generateBox(size: SIMD3<Float>(cardWidth, cardHeight, depth))
        }

        let entity = ModelEntity(mesh: mesh, materials: materials)
        entity.position = position
        entity.orientation = simd_quatf(angle: Float(node.rotationY), axis: SIMD3<Float>(0, 1, 0))
        entity.name = node.id
        entity.components.set(InputTargetComponent())
        entity.components.set(CollisionComponent(shapes: [collisionShape]))
        // Cross-platform highlight: cursor change on Mac, system tint on
        // visionOS. One line, no per-platform branch.
        entity.components.set(HoverEffectComponent())

        if let thumbnailUrl, node.nodeType == .source {
            Task { @MainActor in
                do {
                    let texture = try await MindPalaceTextureCache.shared.texture(for: thumbnailUrl)
                    entity.model?.materials = [UnlitMaterial(texture: texture)]
                } catch {
                    // Keep the colored placeholder when the page image cannot be loaded.
                }
            }
        }

        return entity
    }

    private var pageAspectRatio: Float { 3.0 / 4.0 }

    /// A typed link rendered as a cylinder spanning two node positions.
    /// Cylinder (not box) reads as a 3D tube from any camera angle. Color +
    /// thickness come from the link type and weight.
    private func makeEdgeEntity(
        from: SIMD3<Float>,
        to endPoint: SIMD3<Float>,
        linkType: LinkType,
        weight: Double
    ) -> ModelEntity {
        let delta = endPoint - from
        let length = max(simd_length(delta), 0.0001)
        let thickness: Float = 0.006 * Float(max(0.5, min(weight, 3.0)))
        let mesh = MeshResource.generateCylinder(height: length, radius: thickness)
        let color = MindPalaceTheme.materialColor(for: linkType, alpha: linkType.isSolid ? 0.85 : 0.45)
        let material = SimpleMaterial(color: color, isMetallic: false)
        let entity = ModelEntity(mesh: mesh, materials: [material])
        entity.position = (from + endPoint) / 2
        // generateCylinder is +Y-aligned; rotate +Y onto the link direction.
        entity.orientation = simd_quatf(from: SIMD3<Float>(0, 1, 0), to: delta / length)
        return entity
    }
    #endif
}

#if canImport(RealityKit)
actor MindPalaceTextureCache {
    static let shared = MindPalaceTextureCache()

    private var cache: [URL: TextureResource] = [:]

    func texture(for url: URL) async throws -> TextureResource {
        if let cached = cache[url] { return cached }

        let (data, contentType) = try await fetchImageData(from: url)
        let fileExtension = Self.fileExtension(for: contentType)
        let tempURL = FileManager.default.temporaryDirectory
            .appendingPathComponent(UUID().uuidString)
            .appendingPathExtension(fileExtension)
        try data.write(to: tempURL, options: [.atomic])
        defer { try? FileManager.default.removeItem(at: tempURL) }

        let texture = try await TextureResource.loadAsync(contentsOf: tempURL, withName: nil)
        cache[url] = texture
        return texture
    }

    private func fetchImageData(from url: URL) async throws -> (Data, String) {
        var request = URLRequest(url: url)
        request.addEngineAuth(libraryPath: LibraryManager.shared.globalLibrary?.apiClient.currentLibraryPath)
        let (data, response) = try await URLSession.shared.data(for: request)
        guard let httpResponse = response as? HTTPURLResponse,
              httpResponse.statusCode == 200 else {
            throw URLError(.badServerResponse)
        }
        let contentType = httpResponse.value(forHTTPHeaderField: "Content-Type") ?? "application/octet-stream"
        return (data, contentType)
    }

    private static func fileExtension(for contentType: String) -> String {
        switch contentType.lowercased() {
        case let value where value.contains("png"): return "png"
        case let value where value.contains("jpeg"): return "jpg"
        case let value where value.contains("jpg"): return "jpg"
        case let value where value.contains("webp"): return "webp"
        case let value where value.contains("heic"): return "heic"
        default: return "png"
        }
    }
}
#endif
