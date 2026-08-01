#if canImport(AppKit)
import AppKit
import SwiftUI
import UniformTypeIdentifiers

// MARK: - Content-pane external drop, hit-test-safe by construction (#4458)

/// Feeds external-drop `NSItemProvider`s to the content pane, WITHOUT the
/// hit-testing risk `.onDrop(of:)` carried when it wrapped the whole
/// `NavigationSplitView` (#4184's revert, e66e1bce1's review).
///
/// `.onDrop(of:)`'s risk is inferred — nobody could prove from the hierarchy
/// alone that it wouldn't steal clicks from nested rows. This bridge is safe
/// by CONSTRUCTION instead: `hitTest(_:)` always returns nil, so this view
/// structurally cannot become the target of a click, tap, or any other mouse
/// event — there is no code path in AppKit's responder-chain hit-testing
/// that can route through a view whose own `hitTest` says "not me, try
/// beneath". If drag-destination delivery to a hitTest-nil view turns out
/// not to work in some AppKit version, this degrades to "still misses
/// non-file-url drags" (today's status quo) — never to "clicks are broken",
/// which is the property that actually matters.
///
/// Mirrors `CanvasScrollPan.swift` (#4408), which mirrors the pre-existing
/// `ScrollWheelZoom.swift` (#2713): both are AppKit bridges because SwiftUI
/// has no declarative API for the thing being bridged (a scroll gesture on a
/// non-scroll view there; here, reading `NSItemProvider`s from an
/// `NSDraggingInfo` — `.onDrop(of:)` and `.dropDestination(for:)` are the
/// declarative APIs, and both attach at the SwiftUI view level, which is
/// exactly the level that carried the hit-testing risk).
///
/// Placed in `.background` (not `.overlay`) on the content pane: AppKit
/// resolves an ambiguous drag destination among overlapping views by walking
/// front-to-back, same as ordinary hit-testing — a `.background` view sits
/// BEHIND the foreground content, so any more specific drop target already
/// living in front of it (e.g. a folder cell's own `.dropDestination(for:
/// LibraryItemDrag.self)`, #4124) keeps first claim. This bridge only
/// resolves reads via `NSPasteboard.readObjects(forClasses: [NSItemProvider
/// .self])`, which SwiftUI's Transferable-based internal drags do not
/// populate the same way an external NSItemProvider drag does — internal
/// reorder drags and external file drops are different payload shapes, not
/// just different z-order layers.
struct ContentDropTargetView: NSViewRepresentable {
    let onProviders: ([NSItemProvider]) -> Void

    func makeNSView(context: Context) -> ContentDropCaptureView {
        let view = ContentDropCaptureView()
        view.onProviders = onProviders
        return view
    }

    func updateNSView(_ nsView: ContentDropCaptureView, context: Context) {
        nsView.onProviders = onProviders
    }
}

final class ContentDropCaptureView: NSView {
    var onProviders: (([NSItemProvider]) -> Void)?

    override init(frame frameRect: NSRect) {
        super.init(frame: frameRect)
        // `.item` is UTType's own root — every declared drag type conforms
        // to it, so this registers for anything a drag session can offer,
        // matching `.onDrop(of: [.item])`'s breadth.
        registerForDraggedTypes([NSPasteboard.PasteboardType(UTType.item.identifier)])
    }

    required init?(coder: NSCoder) {
        fatalError("ContentDropCaptureView does not support NSCoder")
    }

    /// The load-bearing override (#4458): NEVER returns self or a subview —
    /// this view structurally cannot intercept a click, tap, or any other
    /// mouse event, regardless of what AppKit's drag-destination resolution
    /// does with it separately.
    override func hitTest(_ point: NSPoint) -> NSView? { nil }

    override func draggingEntered(_ sender: NSDraggingInfo) -> NSDragOperation {
        .copy
    }

    override func performDragOperation(_ sender: NSDraggingInfo) -> Bool {
        let providers = sender.draggingPasteboard.readObjects(
            forClasses: [NSItemProvider.self], options: nil
        ) as? [NSItemProvider] ?? []
        guard !providers.isEmpty else { return false }
        onProviders?(providers)
        return true
    }
}
#endif
