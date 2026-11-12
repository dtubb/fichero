#if os(macOS)
import AppKit

/// A drawn segment box as an accessibility element (#5192): the image overlay and a PDF page make
/// them the same way, so a test or a script asks both surfaces one question.
enum SegmentBoxAccessibility {
    static let identifierPrefix = "SegmentBox-"
    /// The view a page's boxes are drawn in, named for its page (#5193).
    static let pagePrefix = "SegmentPage-"

    static func element(
        segmentId: String, kind: String, frame: CGRect, in parent: NSView, selected: Bool
    ) -> NSAccessibilityElement {
        let element = NSAccessibilityElement()
        element.setAccessibilityRole(.group)
        element.setAccessibilityIdentifier(identifierPrefix + segmentId)
        element.setAccessibilityLabel(kind.capitalized)
        element.setAccessibilityParent(parent)
        element.setAccessibilityFrameInParentSpace(frame)
        element.setAccessibilitySelected(selected)
        return element
    }
}
#endif
