import SwiftUI

/// The ONE on-state a toolbar toggle wears (Daniel, 2026-09-02: every toggle
/// that opens or closes a surface must show the lit outline while that surface
/// is open, "the way the workflow bar and markup bar toggles already do").
///
/// History matters here, because this looks like a reversal and is not. On
/// 2026-08-29 the pane toggles stopped being native `Toggle`s: their on-state
/// filled the control with the accent colour, and "changing colors — that's a
/// bad UX". The words carried the state instead — Show Preview / Hide Preview
/// — which is right, and stays. But words are only legible in the toolbar's
/// Icon-and-Text mode; in Icon Only, four pane buttons, an inspector button
/// and two bar toggles all looked identical whether their surface was up or
/// not, and only the two bar toggles (which had quietly kept an accent GLYPH)
/// told the truth.
///
/// The distinction the 2026-08-29 ruling was really drawing is between a
/// filled control and a lit glyph. This is the lit glyph: the symbol takes the
/// accent tint while the surface is open and `.primary` when it is closed, and
/// nothing around it changes shape or fill. The words keep flipping too, so
/// the state reads in both toolbar modes and without colour.
extension View {
    /// Tint this toolbar control's glyph by whether the surface it governs is
    /// open. `nil`-safe by construction: the closed state is the ordinary
    /// `.primary` every other toolbar glyph uses.
    func toolbarSurfaceLit(_ isOpen: Bool) -> some View {
        foregroundStyle(isOpen ? AnyShapeStyle(Color.accentColor) : AnyShapeStyle(.primary))
    }
}
