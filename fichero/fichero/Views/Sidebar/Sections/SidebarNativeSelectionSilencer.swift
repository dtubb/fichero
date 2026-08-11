import SwiftUI

#if os(macOS)
/// Turns off the sidebar table's NATIVE selection drawing (Daniel,
/// 2026-08-10: keep the grey-platter look "except that flash").
///
/// `selectionHighlightStyle = .none` is a TABLE-level switch: AppKit stops
/// drawing any selection platter and stops flipping selected rows to the
/// emphasized appearance. That removes the dark-accent flash between
/// mouseDown and our grey platter's commit, and lets the disclosure chevron
/// keep its normal dark-grey template color instead of invisible white.
/// Selection tracking, keyboard navigation, and our own listRowBackground
/// platter are untouched.
///
/// Table-level on purpose — the reverted per-row probe (SidebarRowChromeFixer)
/// lost to NSTableRowView recycling; a single setting on the table cannot.
struct SidebarNativeSelectionSilencer: NSViewRepresentable {
    final class Probe: NSView {
        override func viewDidMoveToWindow() {
            super.viewDidMoveToWindow()
            silence()
            // The List's table can mount a beat after the background does.
            DispatchQueue.main.async { [weak self] in self?.silence() }
        }

        func silence() {
            // Nearest-ancestor search so we find the sidebar's OWN table,
            // never the library pane's.
            var node: NSView? = self
            while let current = node {
                if let table = Self.firstTableView(in: current) {
                    if table.selectionHighlightStyle != .none {
                        table.selectionHighlightStyle = .none
                    }
                    return
                }
                node = current.superview
            }
        }

        private static func firstTableView(in root: NSView) -> NSTableView? {
            var queue: [NSView] = [root]
            while !queue.isEmpty {
                let view = queue.removeFirst()
                if let table = view as? NSTableView { return table }
                queue.append(contentsOf: view.subviews)
            }
            return nil
        }
    }

    func makeNSView(context: Context) -> Probe { Probe() }

    func updateNSView(_ probe: Probe, context: Context) {
        probe.silence()
    }
}
#endif
