#if canImport(AppKit)
import AppKit
@testable import Fichero
import Foundation
import Testing

/// The maintainer, 2026-09-27: a selection on the page must look like a Mac selection -- the system's
/// accent and selection colours, dimmed when its pane or window is not the one in front, a crisp line,
/// square handles only while editing, a fainter hover. What breaks without these: a custom colour that
/// ignores the user's accent, Dark Mode and Increase Contrast, or handles offered while reading.
struct SelectionStyleTests {
    @Test("an emphasized selection is the accent and the selected-content colour")
    func emphasizedUsesTheAccent() {
        #expect(SelectionStyle.stroke(emphasized: true) == NSColor.controlAccentColor)
        #expect(SelectionStyle.washBase(emphasized: true) == NSColor.selectedContentBackgroundColor)
    }

    @Test("a selection in a pane or window not in front dims to the unemphasized grey, like Finder's")
    func unemphasizedDims() {
        #expect(SelectionStyle.washBase(emphasized: false) == NSColor.unemphasizedSelectedContentBackgroundColor)
        #expect(SelectionStyle.stroke(emphasized: false) != NSColor.controlAccentColor)
    }

    @Test("hover and plain boxes are the accent too, and hover is fainter than a selection")
    func hoverIsSubtler() {
        #expect(SelectionStyle.hoverBase == NSColor.controlAccentColor)
        #expect(SelectionStyle.boxBase == NSColor.controlAccentColor)
        #expect(SelectionStyle.hoverAlpha < 1)
    }

    @Test("a crisp one-point line, two under Increase Contrast")
    func lineWidths() {
        #expect(SelectionStyle.lineWidth(increaseContrast: false) == 1)
        #expect(SelectionStyle.lineWidth(increaseContrast: true) == 2)
    }

    @Test("eight square handles: the corners and the edge midpoints, none in the middle")
    func handles() {
        let rect = CGRect(x: 100, y: 200, width: 60, height: 40)
        let handles = SelectionStyle.handleRects(around: rect, side: 6)
        #expect(handles.count == 8)
        #expect(handles.allSatisfy { $0.width == 6 && $0.height == 6 })
        let centres = Set(handles.map { "\($0.midX),\($0.midY)" })
        #expect(centres.contains("100.0,200.0") && centres.contains("160.0,240.0"))
        #expect(centres.contains("130.0,200.0") && centres.contains("100.0,220.0"))
        #expect(!centres.contains("130.0,220.0"))
    }

    @Test("editing and focus are part of what is drawn, so changing either redraws")
    func stateRedraws() {
        var editing = DocumentOverlay()
        editing.isEditing = true
        var focused = DocumentOverlay()
        focused.isFocusedPane = true
        #expect(editing != DocumentOverlay())
        #expect(focused != DocumentOverlay())
    }

    /// Inline words are the size of the word they stand for, and never truncated (2026-09-01/02).
    /// A stand-in measure (half the size per character) makes the fitting arithmetic exact.
    @Test("an inline word never runs wider than its box, and a short word takes the box's height")
    func inlineWordsFit() {
        let measure: (String, CGFloat) -> CGSize = { text, size in CGSize(width: CGFloat(text.count) * size * 0.5, height: size) }
        let box = CGRect(x: 0, y: 0, width: 100, height: 20)
        let long = String(repeating: "m", count: 30)
        let longSize = InlineWords.fittedSize(long, in: box, measure: measure)
        #expect(measure(long, longSize).width <= box.width)
        let short = "ok"
        #expect(InlineWords.fittedSize(short, in: box, measure: measure) == box.height * InlineWords.heightFill)
    }

    @Test("a new marquee, or picking one, redraws")
    func marqueesRedraw() {
        var drawn = DocumentOverlay()
        drawn.marquees = [[0.1, 0.1, 0.2, 0.2]]
        #expect(drawn != DocumentOverlay())
        var picked = drawn
        picked.pickedMarquee = 0
        #expect(picked != drawn)
    }

    /// One place for the colours, and no custom colour in it: every value must be a system colour
    /// that follows the accent, Dark Mode and Increase Contrast.
    @Test("the style names no RGB, hex or calibrated colour")
    func noHardCodedColour() throws {
        let source = try String(
            contentsOf: AppSource.root().appendingPathComponent(
                "Views/Preview/ImageViewer/Regions/SelectionStyle.swift"
            ), encoding: .utf8
        )
        // `"#` is a hex string literal; the file's own `#if` is not.
        for banned in ["red:", "srgbRed", "calibratedRed", "deviceRed", "genericRGB", "\"#"] {
            #expect(!source.contains(banned), "SelectionStyle hard-codes a colour: \(banned)")
        }
    }
}
#endif
