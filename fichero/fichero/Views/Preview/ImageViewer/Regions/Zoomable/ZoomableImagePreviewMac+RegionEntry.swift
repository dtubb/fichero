#if os(macOS)
import SwiftUI

// MARK: - Saving a drawn region, and ENTERING a saved one
//
// Daniel, 2026-08-31: "if we draw it, we should be able to save it, and
// double click on it to be taken to a new region." The naming half lives
// in `RegionNaming.swift`; this is the engine half — the child NODE behind a
// promoted region, and the double-click that opens it.

extension ZoomableImagePreview {

    /// One name for one region. Several boxes under a single typed name would
    /// otherwise all answer to it, so a set gets numbered — the name the user
    /// typed stays legible, and each node is still distinguishable.
    ///
    /// `nonisolated` is LOAD-BEARING (#4201): a `static` on a `View` inherits
    /// MainActor under the macOS 26 SDK, and a non-`@MainActor` Swift Testing
    /// suite calling it SIGTRAPs the whole test process.
    nonisolated static func childName(_ name: String, offset: Int, total: Int) -> String {
        guard !name.isEmpty else { return "" }
        return total > 1 ? "\(name) \(offset + 1)" : name
    }

    /// The NODE behind a promoted region: a non-destructive `image.crop_child`
    /// in the PARENT's pixel space (the marquee seam carries the source pixel
    /// size for exactly this denormalization), renamed afterwards when the
    /// user gave a name.
    ///
    /// GAP (2026-08-31): neither `CropOperationRequest` nor the artifact
    /// regions edit request carries a name/title field, so naming cannot ride
    /// the create — it is a second call on the existing document rename path
    /// (`DocumentStore.renameDocumentById`). A failure to name leaves an
    /// honestly-created, default-named child rather than a missing region.
    @MainActor
    func materializeRegionChild(
        parentId: String, rect: [Double], pixelSize: CGSize?, name: String
    ) async {
        guard rect.count >= 4, let documentStore,
              let pixelSize, pixelSize.width > 0, pixelSize.height > 0 else {
            Self.logger.error("Region promote: no pixel size to denormalize \(parentId)")
            return
        }
        let left = max(0, Int((rect[0] * pixelSize.width).rounded(.down)))
        let top = max(0, Int((rect[1] * pixelSize.height).rounded(.down)))
        let width = max(1, Int((rect[2] * pixelSize.width).rounded()))
        let height = max(1, Int((rect[3] * pixelSize.height).rounded()))
        do {
            let service = ImageEditingService(apiClient: documentStore.api)
            let childId = try await service.cropChild(
                documentId: parentId, left: left, top: top, width: width, height: height
            )
            // The parent's cached children now PREDATE this child, and
            // `children(of:)` answers from that cache — a double-click
            // moments later would find no node and silently fall back to a
            // zoom. Drop just this parent's bucket (not the whole cache) so
            // the next read refetches.
            documentStore.childrenCache[parentId] = nil
            guard !name.isEmpty else { return }
            _ = try await documentStore.renameDocumentById(childId, to: name)
        } catch {
            Self.logger.error("Region child create/rename failed: \(String(describing: error))")
        }
    }

    /// ENTER a region (Daniel, 2026-08-31: "double click on it to be taken to
    /// a new region"). A promoted region has a child node whose
    /// `region_in_parent` rect IS this box — that node is what we open, via
    /// the preview's existing `onNavigateToDocument` seam. A box with nothing
    /// behind it (a plain OCR line or word) has nowhere to go, so the honest
    /// answer is to zoom to it rather than invent a node.
    func openRegion(atIndex index: Int) {
        guard let documentId, let boxes = ocrGeometry?.boxes,
              boxes.indices.contains(index) else { return }
        let bbox = boxes[index].bbox
        guard bbox.count >= 4 else { return }
        guard let documentStore, let onNavigateToDocument else {
            imageCoordinator?.zoomToNormalizedRegion(bbox)
            return
        }
        Task { @MainActor in
            let children = await documentStore.children(of: documentId)
            let match = children.first { child in
                guard let region = child.regionInParent, region.isInParentFrame else { return false }
                return RegionInteractionLayer.sameExtent(region.rect, bbox, tolerance: 0.02)
            }
            guard let match else {
                imageCoordinator?.zoomToNormalizedRegion(bbox)
                return
            }
            // The host's id-based navigation only finds documents the library
            // is CURRENTLY listing, so a child that exists but is not listed
            // would be a dead double-click. Stepping the listing into the
            // page is what "taken to a new region" means anyway — the region
            // rows are the page's children.
            let listed = documentStore.currentDocuments.contains { $0.id == match.id }
            if !listed,
               let page = documentStore.currentDocuments.first(where: { $0.id == documentId }) {
                await documentStore.loadChildren(of: page)
            }
            onNavigateToDocument(match.id)
        }
    }
}

#endif
