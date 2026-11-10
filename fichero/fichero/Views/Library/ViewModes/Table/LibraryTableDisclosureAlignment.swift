import SwiftUI

/// Where a disclosure chevron sits inside its row (#6473). AppKit centres the outline cell vertically, so on a
/// row taller than one line it drifts to the middle; it belongs level with the icon and the first line of the name.
enum LibraryTableDisclosureAlignment {
    /// Gap between a row's top edge and the icon's top (the name cell's top inset).
    static let iconTopInset: CGFloat = 3

    /// The chevron's top edge within a row: level with the icon's top, whatever the row's height. A row too short
    /// for that inset (centred is higher) keeps the chevron centred.
    static func chevronY(rowHeight: CGFloat, chevronHeight: CGFloat) -> CGFloat {
        let centred = (rowHeight - chevronHeight) / 2
        return min(centred, iconTopInset)
    }
}

#if os(macOS)
/// Re-seats the library table's disclosure buttons at `LibraryTableDisclosureAlignment.chevronY`. The probe sits in
/// the table's background, finds the backing `NSOutlineView`, and re-applies after each layout pass (AppKit puts
/// the buttons back to centred whenever it lays rows out).
struct LibraryTableDisclosureAligner: NSViewRepresentable {
    final class Probe: NSView {
        private weak var outline: NSOutlineView?
        private var tokens: [NSObjectProtocol] = []

        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            attach()
            DispatchQueue.main.async { [weak self] in self?.attach() }
        }

        func attach() {
            var node: NSView? = self
            while let current = node {
                if let found = Self.firstOutline(in: current) {
                    if found !== outline {
                        tokens.forEach(NotificationCenter.default.removeObserver)
                        outline = found
                        found.postsFrameChangedNotifications = true
                        tokens = [
                            NotificationCenter.default.addObserver(
                                forName: NSView.frameDidChangeNotification, object: found, queue: .main
                            ) { [weak self] _ in MainActor.assumeIsolated { self?.align() } },
                            NotificationCenter.default.addObserver(
                                forName: NSOutlineView.itemDidExpandNotification, object: found, queue: .main
                            ) { [weak self] _ in MainActor.assumeIsolated { self?.align() } },
                        ]
                    }
                    align()
                    return
                }
                node = current.superview
            }
        }

        func align() {
            guard let outline else { return }
            for row in 0..<outline.numberOfRows {
                guard let rowView = outline.rowView(atRow: row, makeIfNecessary: false) else { continue }
                for button in rowView.subviews where button.identifier == NSOutlineView.disclosureButtonIdentifier {
                    let height = button.frame.height
                    let y = LibraryTableDisclosureAlignment.chevronY(rowHeight: rowView.bounds.height, chevronHeight: height)
                    let flippedY = rowView.isFlipped ? y : rowView.bounds.height - y - height
                    if abs(button.frame.origin.y - flippedY) > 0.5 { button.setFrameOrigin(NSPoint(x: button.frame.origin.x, y: flippedY)) }
                }
            }
        }

        deinit { tokens.forEach(NotificationCenter.default.removeObserver) }

        private static func firstOutline(in root: NSView) -> NSOutlineView? {
            var queue: [NSView] = [root]
            while !queue.isEmpty {
                let view = queue.removeFirst()
                if let outline = view as? NSOutlineView { return outline }
                queue.append(contentsOf: view.subviews)
            }
            return nil
        }
    }

    func makeNSView(context: Context) -> Probe { Probe() }
    func updateNSView(_ probe: Probe, context: Context) { probe.attach() }
}
#endif
