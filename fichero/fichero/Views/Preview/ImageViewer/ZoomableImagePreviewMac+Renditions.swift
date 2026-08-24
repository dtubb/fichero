#if os(macOS)
import SwiftUI

/// Which rendition a page OPENS on (Daniel, 2026-08-23: "background removed is
/// the best one, so default to that. it's background removed < enhanced <
/// page"). The sticky role wins — a reader who flipped to a rendition stays in
/// that KIND across left/right sibling steps ("if I'm in background removed, I
/// see that as I go left and right") — then the quality ranking, then the
/// engine's order (index 0, primary first). File scope so tests run off-main.
func preferredRenditionIndex(in renditions: [DocumentRendition], stickyRole: String?) -> Int {
    if let stickyRole,
       let idx = renditions.firstIndex(where: { $0.role == stickyRole }) {
        return idx
    }
    for role in ["background_removed", "enhanced"] {
        if let idx = renditions.firstIndex(where: { $0.role == role }) {
            return idx
        }
    }
    return 0
}

/// The overlay frame matrix (2026-08-23 entry-scoped runs) — match-or-SKIP,
/// never transform. A predicate over the displayed pixels cannot be wrong
/// about a frame it does not compute:
/// - `required == nil` (the document's own frame): draws on the base image
///   and on any rendition that keeps that frame; skips a rendition with its
///   own frame (crop/rotate/deskew).
/// - `required != nil`: draws ONLY when exactly that rendition's pixels are
///   on screen. Note a region node's BASE display serves its parent's full
///   pixels, so a crop-framed set stays dark there — deliberately: blank
///   beats a plausible band in the wrong frame. Compose-through-region lands
///   here with the ladder work. File scope so the matrix is pinned off-main.
func overlayFrameMatches(
    required: String?,
    displayed: String?,
    displayedHasOwnFrame: Bool
) -> Bool {
    guard let required else { return !displayedHasOwnFrame }
    return required == displayed
}

extension ZoomableImagePreview {
    /// Load this page's renditions (2026-08-20 bbox review).
    ///
    /// The list arrives in ENGINE order — primary first, then role preference,
    /// then a deterministic tiebreak — and is used as delivered. Re-sorting
    /// client-side would recreate exactly the disagreement about what "next"
    /// means that deciding the order server-side exists to prevent.
    ///
    /// Lives here so the (large) preview struct body stays under the
    /// type-body-length budget, same reason `loadOCRGeometry` moved out.
    func loadRenditions() async {
        renditions = []
        renditionIndex = 0
        renditionOverrideImage = nil
        guard let documentId, let renditionService else { return }
        // Only renditions whose bytes are expected to exist: a
        // referenced-but-absent staging entry is a knowable state in the
        // model, but it should never become a step in a flip sequence.
        await renditionService.load(documentId: documentId)
        renditions = renditionService.displayable(documentId: documentId)
        // Land on the preferred rendition, not blindly on engine-index 0: the
        // reader's current KIND is sticky across sibling steps, and a fresh
        // page opens on the best available (background removed > enhanced >
        // original). Selection only — flipRendition fetches the pixels.
        let sticky = UserDefaults.standard.string(forKey: Self.stickyRenditionRoleKey)
        let preferred = preferredRenditionIndex(in: renditions, stickyRole: sticky)
        // Preferred-first (2026-08-24): when the canvas already fetched the
        // preferred rendition's pixels, LAND there — index, override image,
        // no second fetch, no third visible swap per sibling step.
        if let renderedRenditionId,
           renditions.indices.contains(preferred),
           renditions[preferred].id == renderedRenditionId {
            renditionIndex = preferred
            renditionOverrideImage = renderedImage
            if let renderedImage { imageSize = renderedImage.size }
        } else if preferred != 0 {
            flipRendition(to: preferred, recordSticky: false)
        }
    }

    /// UserDefaults, not @State: the sticky KIND must survive the view being
    /// rebuilt per sibling — which is exactly when it is needed.
    static var stickyRenditionRoleKey: String { "preview.stickyRenditionRole" }

    /// The rendition whose PIXELS are on screen, or nil when the base image is.
    var displayedRenditionId: String? {
        guard renditionOverrideImage != nil,
              renditions.indices.contains(renditionIndex) else { return nil }
        return renditions[renditionIndex].id
    }

    /// Whether an OCR box set may be drawn over the current pixels. Match-or-
    /// SKIP, never transform — see `overlayFrameMatches` for the matrix.
    func geometryFrameMatchesDisplay(_ geometry: OCRGeometry) -> Bool {
        let displayedOwnFrame = renditionOverrideImage != nil
            && renditions.indices.contains(renditionIndex)
            && renditions[renditionIndex].hasOwnFrame
        return overlayFrameMatches(
            required: geometry.renditionId,
            displayed: displayedRenditionId,
            displayedHasOwnFrame: displayedOwnFrame
        )
    }

    /// What the toolbar shows about the current rendition.
    ///
    /// `nil` when there is nothing worth saying — no service, no document, or
    /// a page with a single rendition, where naming it would be noise. The
    /// toolbar hides the whole section in that case rather than greying it.
    var renditionNav: ReaderRenditionNav? {
        guard renditions.count > 1 else { return nil }
        let index = min(max(renditionIndex, 0), renditions.count - 1)
        let current = renditions[index]
        // The flip is LIVE (2026-08-21): the engine serves rendition bytes
        // now, so the closures exist exactly at the sequence edges — their
        // presence is the capability, no separate canGo* flags.
        return ReaderRenditionNav(
            name: current.displayName,
            index: index,
            count: renditions.count,
            hasOwnFrame: current.hasOwnFrame,
            goPrevious: index > 0 ? { self.flipRendition(to: index - 1) } : nil,
            goNext: index < renditions.count - 1 ? { self.flipRendition(to: index + 1) } : nil
        )
    }

    /// Show one rendition of the SAME page — the up/down axis (Daniel: "the
    /// way we want to change between renditions is swiping up and down";
    /// arrow keys land first, the swipe gesture layers on the same call).
    /// Left/right stays sibling-page navigation. Fetch, decode off-main,
    /// swap in place — the same no-blank-frame contract as page flips.
    /// `recordSticky` is false for the automatic landing in `loadRenditions` —
    /// only a USER flip may change which kind follows them across siblings.
    func flipRendition(to targetIndex: Int, recordSticky: Bool = true) {
        guard let documentId, let renditionService,
              renditions.indices.contains(targetIndex),
              targetIndex != renditionIndex else { return }
        let target = renditions[targetIndex]
        if recordSticky {
            UserDefaults.standard.set(target.role, forKey: Self.stickyRenditionRoleKey)
            // Only a user flip parks the flip animation; the automatic landing
            // rides the page-step swap already in flight — parking here too
            // would double-animate every sibling step.
            PreviewSwapAnimation.park(.renditionFlip(forward: targetIndex > renditionIndex))
        }
        renditionIndex = targetIndex
        Task {
            do {
                let data = try await renditionService.contentData(
                    documentId: documentId, renditionId: target.id
                )
                guard self.renditionIndex == targetIndex else { return }  // a newer flip won
                if let img = NSImage(data: data) {
                    self.renditionOverrideImage = img
                    self.imageSize = img.size
                } else {
                    Self.logger.error(
                        "Rendition \(target.id) bytes could not be decoded as an image"
                    )
                }
            } catch {
                // Never swallowed: a failed flip leaves the current pixels up
                // and says why, instead of a silent no-op chevron.
                Self.logger.error(
                    "Rendition flip to \(target.id) failed: \(String(describing: error))"
                )
            }
        }
    }
}
#endif
