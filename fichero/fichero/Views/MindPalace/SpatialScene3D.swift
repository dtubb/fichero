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
    @Binding var selectedNodeId: String?

    #if canImport(RealityKit)
    @State private var cameraDistance = 5.5
    @State private var orbitYaw = 0.0
    @State private var orbitPitch = 0.0
    @State private var dragStart = CGSize.zero
    @State private var magnificationStart = 1.0
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
        .background(Color(nsColor: .textBackgroundColor))
        #else
        Spatial2DCanvas(nodes: nodes, connections: connections, selectedNodeId: $selectedNodeId)
        #endif
        }
    }

    #if canImport(RealityKit)
    private var cameraDragGesture: some Gesture {
        DragGesture(minimumDistance: 2)
            .onChanged { value in
                let deltaWidth = value.translation.width - dragStart.width
                let deltaHeight = value.translation.height - dragStart.height
                orbitYaw += Double(deltaWidth) * 0.008
                orbitPitch = min(1.15, max(-1.15, orbitPitch + Double(deltaHeight) * 0.008))
                dragStart = value.translation
            }
            .onEnded { _ in
                dragStart = .zero
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

        for connection in connections {
            guard
                let from = positions[connection.sourceNodeId],
                let toEnd = positions[connection.targetNodeId]
            else { continue }
            root.addChild(makeEdgeEntity(from: from, to: toEnd, type: connection.connectionType))
        }

        return root
    }

    private func makeNodeEntity(_ node: MindPalaceNode, at position: SIMD3<Float>) -> ModelEntity {
        let scale = Float(max(node.scale, 0.25))
        let cardWidth: Float = 0.8 * scale
        let cardHeight: Float = cardWidth / pageAspectRatio
        let thumbnailUrl = node.thumbnailUrl
        let mesh: MeshResource
        let materials: [any Material]

        if thumbnailUrl != nil || node.nodeType == .source {
            mesh = MeshResource.generatePlane(
                width: cardWidth,
                height: cardHeight,
                cornerRadius: min(cardWidth, cardHeight) * 0.07
            )
            materials = [UnlitMaterial(color: nsColor(for: node.nodeType))]
        } else {
            let depth: Float = cardWidth * 0.12
            mesh = MeshResource.generateBox(
                size: SIMD3<Float>(cardWidth, cardHeight, depth),
                cornerRadius: min(cardWidth, cardHeight, depth) * 0.18
            )
            materials = [SimpleMaterial(color: nsColor(for: node.nodeType), isMetallic: false)]
        }

        let entity = ModelEntity(mesh: mesh, materials: materials)
        entity.position = position
        entity.orientation = simd_quatf(angle: Float(node.rotationY), axis: SIMD3<Float>(0, 1, 0))
        entity.name = node.id
        entity.components.set(InputTargetComponent())
        entity.components.set(
            CollisionComponent(
                shapes: [ShapeResource.generateBox(size: SIMD3<Float>(cardWidth, cardHeight, cardWidth * 0.12))]
            )
        )

        if let thumbnailUrl {
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

    /// A connection rendered as a thin box spanning the two node positions.
    private func makeEdgeEntity(
        from: SIMD3<Float>,
        to endPoint: SIMD3<Float>,
        type: MindPalaceConnectionType
    ) -> ModelEntity {
        let delta = endPoint - from
        let length = simd_length(delta)
        let thickness: Float = 0.01
        let mesh = MeshResource.generateBox(size: SIMD3<Float>(thickness, thickness, max(length, 0.0001)))
        let material = SimpleMaterial(color: nsColor(for: type).withAlphaComponent(0.6), isMetallic: false)
        let entity = ModelEntity(mesh: mesh, materials: [material])
        entity.position = (from + endPoint) / 2
        if length > 0 {
            // Orient the box's local +Z axis along the connection direction.
            entity.orientation = simd_quatf(from: SIMD3<Float>(0, 0, 1), to: delta / length)
        }
        return entity
    }

    private func nsColor(for type: MindPalaceNodeType) -> NSColor {
        switch type {
        case .source: return .systemBlue
        case .claim: return .systemPurple
        case .note: return .systemOrange
        case .entity: return .systemGreen
        case .transcription: return .systemTeal
        case .unknown: return .systemGray
        }
    }

    private func nsColor(for type: MindPalaceConnectionType) -> NSColor {
        switch type {
        case .evidentiary: return .systemBlue
        case .semantic: return .systemPurple
        case .ontological: return .systemGreen
        case .hermeneutic: return .systemOrange
        case .userDrawn: return .systemGray
        case .unknown: return .secondaryLabelColor
        }
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
