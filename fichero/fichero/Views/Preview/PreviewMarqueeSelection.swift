import CoreGraphics
import Foundation
import Observation

/// Shared holder for an EPHEMERAL marquee selection drawn in Preview — a crop
/// that is not (yet) a persisted node (Daniel, 2026-08-29: when present it is
/// the topmost rung of the workflow bar's scope ladder; the chip says
/// "a selection of 4_Hoja_531_Verso" and ▶ runs on that crop).
///
/// The execution path cannot take a bare rect — crops are per-node CONFIG in
/// the engine (zoom's region mode, detect_regions), never run inputs — so the
/// run materializes the selection as a real region child at ▶-press via
/// `POST /api/images/{id}/crop` (`image.crop_child`: non-destructive, carries
/// `region_in_parent` with "user-crop" confidence). That endpoint takes PIXEL
/// coordinates, which is why this seam carries the source's pixel size next
/// to the normalized rect.
///
/// SHARED SEAM, writer pending (preview-regions lane): the Preview's marquee
/// gesture is owned by that worker; it writes here on drag-end and calls
/// `clear()` on Esc / click-away / document switch. This lane only READS it.
/// A process-wide shared instance for now, mirroring `FocusedArtifact.shared`;
/// if the sibling needs per-window instances, keep this type and move the
/// instance into per-window state.
@Observable
@MainActor
final class PreviewMarqueeSelection {
    static let shared = PreviewMarqueeSelection()

    /// The document the marquee was drawn on.
    private(set) var documentId: String?

    /// Human label for that document, so the chip can name the scope
    /// without a store lookup.
    private(set) var documentName: String?

    /// The drawn rect in the source image's normalized (0–1) space.
    private(set) var normalizedRect: CGRect?

    /// The source image's pixel dimensions the rect was measured against —
    /// what lets ▶ denormalize into the crop endpoint's pixel coordinates.
    private(set) var imagePixelSize: CGSize?

    init() {}

    var isActive: Bool { documentId != nil && normalizedRect != nil }

    func select(
        documentId: String,
        documentName: String?,
        normalizedRect: CGRect,
        imagePixelSize: CGSize?
    ) {
        self.documentId = documentId
        self.documentName = documentName
        self.normalizedRect = normalizedRect
        self.imagePixelSize = imagePixelSize
    }

    func clear() {
        documentId = nil
        documentName = nil
        normalizedRect = nil
        imagePixelSize = nil
    }
}
