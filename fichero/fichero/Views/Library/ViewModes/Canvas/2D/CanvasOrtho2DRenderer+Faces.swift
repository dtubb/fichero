import ImageIO
import RealityKit
import SwiftUI

// MARK: - Folder and note cards (Daniel, 2026-10-11: plain blue tiles with nothing in them)

/// A folder's or a note's card wears its face (`CanvasCardFace`): its own colour, its name, and what it holds or
/// says, drawn by SwiftUI into the card's texture. A folder's face fills in the pictures of what it holds as they
/// load. A page's card is untouched: it shows its own picture (+Thumbnails.swift).
extension CanvasOrtho2DRenderer {
    /// The faces for the board now: a card whose face changed is redrawn in place, and the folders' pictures load.
    func setFaces(_ newFaces: [String: CanvasCardFace]) {
        guard newFaces != faces else { return }
        let changed = Set(newFaces.keys).union(faces.keys).filter { newFaces[$0] != faces[$0] }
        faces = newFaces
        for id in changed where placeablesById[id] != nil { reskinCard(id) }
        loadFacePictures()
    }

    /// Draw a card's face into its texture; nothing for a card without one.
    func drawFace(_ id: String, into entity: ModelEntity) {
        guard let face = faces[id], let image = face.image(pictures: facePictures) else { return }
        Task { @MainActor in
            guard let texture = try? await TextureResource(image: image, options: .init(semantic: .color)) else {
                return
            }
            entity.model?.materials = [UnlitMaterial(texture: texture)]
            texturedIds.insert(id)
        }
    }

    /// Load the pictures the folders' faces show (up to four each, through the library's own storage), then redraw
    /// the faces that hold them.
    func loadFacePictures() {
        let wanted = Set(faces.values.flatMap(\.pictureIds)).subtracting(facePictures.keys)
        guard !wanted.isEmpty, let storageService else { return }
        Task { @MainActor in
            for id in wanted {
                guard let data = try? await storageService.thumbnailData(for: id),
                      let source = CGImageSourceCreateWithData(data as CFData, nil),
                      let image = CGImageSourceCreateImageAtIndex(source, 0, nil) else { continue }
                facePictures[id] = image
            }
            for (cardId, face) in faces where !wanted.isDisjoint(with: face.pictureIds) {
                if let entity = placedEntity(cardId) as? ModelEntity { drawFace(cardId, into: entity) }
            }
        }
    }
}

extension CanvasCardFace {
    /// The pictures this face shows, by item id (a folder's); none for a note.
    var pictureIds: [String] {
        if case .folder(_, _, let ids) = content { return ids }
        return []
    }
}
