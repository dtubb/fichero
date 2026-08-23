import Foundation
import RealityKit
import SwiftUI

// MARK: - Painting the colour channel (§20.3 Colour by)

/// Turns a `CanvasTint` slot into the colour a card actually shows, for BOTH
/// renderers — the hue twin of `CanvasEmphasisPainter`.
///
/// **Where the colour lands, and what yields to what.** A card at `.glyph` has
/// no page texture: it IS its base colour, so that is where a colour field does
/// §20.2's work — 2,228 cards as one colour map, which is the distribution
/// instrument the whole arrangement is for. From `.thumbnail` up the page image
/// covers the face, and there **page legibility outranks the encoding**: the
/// tint yields entirely rather than multiplying over a scan and muddying the
/// paper the user came to read. Colouring a textured card is not forbidden by
/// anything here, but it wants an EDGE treatment (a coloured mat around the
/// card) rather than a multiply, and that is a design decision with its own
/// geometry cost — deliberately not made tonight.
///
/// ponytail: the un-textured cards are repainted by swapping the material's
/// colour, which is safe precisely BECAUSE there is no texture to lose. A
/// textured card is never touched, so #4409 cannot fire from this channel at
/// all — not "suppressed", structurally absent.
@MainActor
enum CanvasTintPainter {
    /// System-semantic colours only, per the house rule — no hand-rolled
    /// ramps. Eight, matching `CanvasTint.paletteSize`: a legend the eye can
    /// hold beats a unique colour per value, and categorical colours stop being
    /// distinguishable past about this many.
    ///
    /// `nonisolated`, and a switch rather than a stored array, for two reasons
    /// that turn out to be one: a palette lookup is pure arithmetic over a
    /// fixed list and has no business demanding the main actor, and a static
    /// array of a non-Sendable colour type is exactly the kind of shared
    /// mutable-looking state strict concurrency is right to object to.
    nonisolated static func color(forSlot slot: Int) -> PlatformColor {
        switch ((slot % CanvasTint.paletteSize) + CanvasTint.paletteSize) % CanvasTint.paletteSize {
        case 0: .systemBlue
        case 1: .systemOrange
        case 2: .systemGreen
        case 3: .systemPurple
        case 4: .systemTeal
        case 5: .systemPink
        case 6: .systemIndigo
        default: .systemBrown
        }
    }

    /// Paint one card, or leave it at `fallback` (its kind tint) when the tint
    /// channel has nothing to say about it.
    ///
    /// `isTextured` is the renderer's answer to "does this card currently carry
    /// a page image?" — a textured card is skipped, so the page stays readable.
    static func apply(
        _ tint: CanvasTint, to entity: ModelEntity, id: String,
        fallback: PlatformColor, isTextured: Bool
    ) {
        guard !isTextured else { return }
        let color = tint.slot(for: id).map(color(forSlot:)) ?? fallback
        entity.model?.materials = [UnlitMaterial(color: color)]
    }
}
