import CoreGraphics
import SwiftUI
#if os(macOS)
import AppKit
#endif

/// A box's colour (`segment-editor.md` "Box colour and the segment hierarchy", #5467 part b): ONE function,
/// on every platform, for every surface that colours a box -- the Preview overlay, the PDF page, the
/// Inspector's rows. `RegionColours` decides the tone; this turns it into a SYSTEM colour, so each adapts to
/// Light, Dark and Increase Contrast. No RGB here either.
extension SelectionStyle {
    /// The hues, in the order regions take them (`RegionColours.paletteCount` long).
    static let regionPalette: [PlatformColor] = [
        .systemBlue, .systemOrange, .systemGreen, .systemPurple, .systemPink, .systemTeal,
        .systemIndigo, .systemBrown, .systemMint, .systemCyan, .systemRed, .systemYellow
    ]

    /// The palette's NAMES, parallel to `regionPalette`: what a surface that cannot hold an `NSColor` is sent
    /// (the Reader's served page maps each to WebKit's `-apple-system-<name>`), and what a region's own set
    /// colour stores -- never RGB, so every surface still adapts to the appearance.
    nonisolated static let regionPaletteNames: [String] = [
        "blue", "orange", "green", "purple", "pink", "teal",
        "indigo", "brown", "mint", "cyan", "red", "yellow"
    ]

    /// A tone's palette name (`regionPaletteNames`).
    nonisolated static func regionPaletteName(_ tone: RegionColours.Tone) -> String {
        regionPaletteNames[tone.hue % regionPaletteNames.count]
    }

    /// A box's colour: its region's hue at its reading-order strength, times `opacity`; the plain box colour
    /// (the accent) when it has no tone (artifact geometry, which has no regions).
    static func regionColour(_ tone: RegionColours.Tone?, opacity: CGFloat = 1) -> PlatformColor {
        guard let tone else { return plainBox.withAlphaComponent(opacity) }
        return regionPalette[tone.hue % regionPalette.count].withAlphaComponent(CGFloat(tone.strength) * opacity)
    }

    /// A box with no region: the accent (the Mac's own accent colour; the tint on iOS).
    private static var plainBox: PlatformColor {
        #if os(macOS)
        .controlAccentColor
        #else
        .tintColor
        #endif
    }

    /// A region's legend swatch: its hue as a strip graded from full strength to `RegionColours.lightestStrength`,
    /// the shade its lines take along the reading order (#5426). Drawn at display time from the system colour,
    /// so it adapts to the appearance; an image because a menu item draws only an image beside its title.
    static func regionLegendSwatch(hue: Int) -> Image {
        #if os(macOS)
        // The system colours, made here; each resolves for the appearance when the handler draws it.
        let steps = 5
        let colours = (0..<steps).map { step in
            regionColour(RegionColours.Tone(
                hue: hue, strength: 1 - (1 - RegionColours.lightestStrength) * Double(step) / Double(steps - 1)
            ))
        }
        let image = NSImage(size: NSSize(width: 28, height: 10), flipped: false) { rect in
            let width = rect.width / CGFloat(colours.count)
            for (step, colour) in colours.enumerated() {
                colour.setFill()
                NSBezierPath(rect: NSRect(x: CGFloat(step) * width, y: 0, width: width, height: rect.height)).fill()
            }
            return true
        }
        image.isTemplate = false
        return Image(nsImage: image)
        #else
        return Image(systemName: "circle.fill")
        #endif
    }

    /// The same colour for a SwiftUI swatch (the Inspector's rows).
    static func regionSwatch(_ tone: RegionColours.Tone?) -> Color {
        Color(platformColor: regionColour(tone))
    }
}

/// How a segment's box, its selection and its hover look on the page -- in ONE place, so every
/// overlay layer uses the same values (the maintainer, 2026-09-27: the old look was "not Mac OS X
/// enough").
///
/// The system's own selection language, never custom colours: the accent colour and
/// `selectedContentBackgroundColor` while the pane is the one being worked in and its window is key,
/// and the grey `unemphasizedSelectedContentBackgroundColor` otherwise -- the way Finder and Preview
/// dim a selection in a window that is not in front. Every colour is a SYSTEM colour resolved at draw
/// time, so it follows the user's accent colour, Dark Mode and Increase Contrast by itself. No RGB
/// appears in this file, and a test says so.
enum SelectionStyle {}

#if os(macOS)
extension SelectionStyle {
    // MARK: Colours -- system colours only

    /// The selection's outline.
    static func stroke(emphasized: Bool) -> NSColor {
        emphasized ? .controlAccentColor : .secondaryLabelColor
    }

    /// The selection's wash, before its alpha.
    static func washBase(emphasized: Bool) -> NSColor {
        emphasized ? .selectedContentBackgroundColor : .unemphasizedSelectedContentBackgroundColor
    }

    /// Light: the page under a selection must stay readable.
    static func washAlpha(emphasized: Bool) -> CGFloat { emphasized ? 0.18 : 0.3 }

    /// The hover outline: the accent, fainter than a selection and with no wash.
    static let hoverBase: NSColor = .controlAccentColor
    static let hoverAlpha: CGFloat = 0.55

    /// An unselected box: the accent, faint, its stroke dimmed by how sure the machine is.
    static let boxBase: NSColor = .controlAccentColor

    /// The wash under a hovered box: a fill only on hover or selection, never at rest (#5207).
    static let hoverWashAlpha: CGFloat = 0.1

    /// A resize handle's fill: the control background (white in Light Mode, dark in Dark Mode), with
    /// the selection's stroke around it, as Preview draws its shape handles.
    static let handleFill: NSColor = .controlBackgroundColor

    // MARK: Geometry -- in SCREEN points, divided by the magnification when drawn

    /// A crisp one-point line; two under Increase Contrast.
    static func lineWidth(increaseContrast: Bool) -> CGFloat { increaseContrast ? 2 : 1 }

    static let handleSide: CGFloat = 6

    /// The eight square handles of a selected box in Edit Segments: four corners and four edge
    /// midpoints, each `side` across and centred on its point. `rect` and `side` in the same space.
    static func handleRects(around rect: CGRect, side: CGFloat) -> [CGRect] {
        let columns = [rect.minX, rect.midX, rect.maxX]
        let rows = [rect.minY, rect.midY, rect.maxY]
        var out: [CGRect] = []
        for column in columns {
            for row in rows where !(column == rect.midX && row == rect.midY) {
                out.append(CGRect(x: column - side / 2, y: row - side / 2, width: side, height: side))
            }
        }
        return out
    }
}
#endif
