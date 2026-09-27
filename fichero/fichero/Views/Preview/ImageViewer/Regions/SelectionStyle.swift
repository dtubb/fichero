#if os(macOS)
import AppKit
import CoreGraphics

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
enum SelectionStyle {
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
    static let boxWashAlpha: CGFloat = 0.06

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
