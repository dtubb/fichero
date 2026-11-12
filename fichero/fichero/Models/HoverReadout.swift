import CoreGraphics
import Foundation

/// The page's text readouts (#6422, `source.editor.hover-and-selection-keep-the-region-colour`): the Display menu's
/// **Show Text on Hover** (off by default; when on, the label waits for the pointer to rest, as a help tag does) and
/// **Show Text of the Selection** (the selected boxes' words, without hovering). Pure: the layer asks, this answers.
enum HoverReadout {
    static let hoverKey = "preview.showTextOnHover"
    static let selectionKey = "preview.showTextOfSelection"
    /// How long the pointer rests before the hover label shows, as a help tag waits.
    static let restDelay: Duration = .milliseconds(600)
    /// The most selected boxes labelled at once: a band over a page must not bury it in labels.
    static let selectionCap = 3

    static var showsOnHover: Bool { UserDefaults.standard.bool(forKey: hoverKey) }
    static var showsSelection: Bool { UserDefaults.standard.bool(forKey: selectionKey) }

    /// The hover label shows only with the switch on and once the pointer has rested where it is now.
    static func showsHover(enabled: Bool, pointer: CGPoint?, rested: CGPoint?) -> Bool {
        enabled && pointer != nil && pointer == rested
    }

    /// The selected boxes that get a label: with the switch on, the first few with words, in the order drawn.
    static func labelledSelection<Box>(
        _ boxes: [Box], selected: Set<String>, enabled: Bool, id: (Box) -> String?, text: (Box) -> String
    ) -> [Box] {
        guard enabled, !selected.isEmpty else { return [] }
        return Array(boxes.filter { box in id(box).map(selected.contains) == true && !text(box).isEmpty }.prefix(selectionCap))
    }
}
