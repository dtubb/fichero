#if os(macOS)
import AppKit
import Foundation

/// What a window DRAWS, read from its views and their accessibility elements -- never from a store
/// (#5193, `ui-testing.describe-window`). On 2026-09-28 every test was green while a window drew no
/// boxes; this is the reading that would have said so: the panes shown, and for each page on screen the
/// segment ids whose boxes are drawn (`SegmentBox-<id>`, #5192), with their frames and the selection.
@MainActor
enum WindowDescription {
    struct Box: Codable, Equatable {
        let segment: String
        let kind: String
        /// Screen frame `[x, y, width, height]`, as accessibility reports it.
        let frame: [Double]
        let selected: Bool
    }

    struct Page: Codable, Equatable {
        let id: String
        let boxes: [Box]
    }

    struct Description: Codable, Equatable {
        let panes: [String]
        /// The selected segment ids, as the drawn boxes say.
        let selection: [String]
        let pages: [Page]
    }

    static func describe(_ root: NSView) -> Description {
        var panes: [String] = []
        var pages: [Page] = []
        var seen = Set<ObjectIdentifier>()
        func visit(_ node: Any) {
            guard let object = node as? NSObject, seen.insert(ObjectIdentifier(object)).inserted else { return }
            if let pane = identifier(of: object), pane.hasPrefix("pane.") { panes.append(String(pane.dropFirst(5))) }
            if let view = object as? NSView, let page = pageId(of: view) {
                pages.append(Page(id: page, boxes: boxes(drawnIn: view)))
            }
            children(of: object).forEach(visit)
            (object as? NSView)?.subviews.forEach(visit)
        }
        visit(root)
        let selection = pages.flatMap(\.boxes).filter(\.selected).map(\.segment)
        return Description(panes: panes, selection: selection, pages: pages)
    }

    static func json(_ description: Description) -> String {
        let encoder = JSONEncoder()
        encoder.outputFormatting = [.sortedKeys]
        return (try? encoder.encode(description)).flatMap { String(bytes: $0, encoding: .utf8) } ?? "{}"
    }

    /// A page's view: the image overlay named `SegmentPage-<id>`, or a PDF view that knows its page.
    private static func pageId(of view: NSView) -> String? {
        if let pdf = view as? PinchOwningPDFView { return pdf.segmentPageId }
        let name = view.accessibilityIdentifier()
        return name.hasPrefix(SegmentBoxAccessibility.pagePrefix)
            ? String(name.dropFirst(SegmentBoxAccessibility.pagePrefix.count)) : nil
    }

    private static func boxes(drawnIn view: NSView) -> [Box] {
        (view.accessibilityChildren() ?? []).compactMap { child in
            guard let element = child as? NSAccessibilityElement,
                  let name = element.accessibilityIdentifier(), name.hasPrefix(SegmentBoxAccessibility.identifierPrefix)
            else { return nil }
            let frame = element.accessibilityFrame()
            return Box(
                segment: String(name.dropFirst(SegmentBoxAccessibility.identifierPrefix.count)),
                kind: element.accessibilityLabel() ?? "",
                frame: [frame.minX, frame.minY, frame.width, frame.height].map { Double($0) },
                selected: element.isAccessibilitySelected()
            )
        }
    }

    /// Any accessibility node's identifier and children -- SwiftUI's nodes are not NSViews, so asked by
    /// selector, only when the node answers it.
    private static func identifier(of object: NSObject) -> String? {
        if let view = object as? NSView { return view.accessibilityIdentifier() }
        return perform(object, "accessibilityIdentifier") as? String
    }

    private static func children(of object: NSObject) -> [Any] {
        if let view = object as? NSView { return view.accessibilityChildren() ?? [] }
        return perform(object, "accessibilityChildren") as? [Any] ?? []
    }

    private static func perform(_ object: NSObject, _ name: String) -> Any? {
        let selector = NSSelectorFromString(name)
        guard object.responds(to: selector) else { return nil }
        return object.perform(selector)?.takeUnretainedValue()
    }
}

#if DEBUG
/// `describe window` (Debug-only test suite, `FicheroDebug.sdef`, #5193): the key window as
/// `WindowDescription` JSON. Compiled out of Release, and the Release dictionary does not name it.
@objc(FicheroDescribeWindowCommand)
class FicheroDescribeWindowCommand: NSScriptCommand {
    override func performDefaultImplementation() -> Any? {
        MainActor.assumeIsolated {
            guard let root = (NSApp.keyWindow ?? NSApp.windows.first { $0.isVisible })?.contentView else {
                scriptErrorNumber = NSInternalScriptError
                scriptErrorString = "No visible window to describe -- is a library window open?"
                return nil
            }
            return WindowDescription.json(WindowDescription.describe(root))
        }
    }
}
#endif
#endif
