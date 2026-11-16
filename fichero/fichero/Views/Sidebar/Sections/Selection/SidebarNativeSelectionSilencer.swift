import SwiftUI

#if os(macOS)
/// Turns off the sidebar table's NATIVE selection drawing (Daniel,
/// 2026-08-10: keep the grey-platter look "except that flash"; 2026-10-11:
/// the sidebar's selection is never blue, in any focus state).
///
/// `selectionHighlightStyle = .none` is a TABLE-level switch: AppKit stops
/// drawing any selection platter and stops flipping selected rows to the
/// emphasized appearance (the accent fill, white bold text) whether or not
/// the table is first responder in the key window. Selection tracking,
/// keyboard navigation, and our own listRowBackground platter are untouched.
///
/// Set once was not enough (Daniel's screenshot, 2026-10-11: Sources selected
/// in accent with white text): the List puts its own style back on the table
/// after we set ours. So the probe OBSERVES the setting and puts `.none` back
/// the moment anything changes it, and re-checks on every selection change.
///
/// Table-level on purpose — the reverted per-row probe (SidebarRowChromeFixer)
/// lost to NSTableRowView recycling; a single setting on the table cannot.
struct SidebarNativeSelectionSilencer: NSViewRepresentable {
    /// Changes with the selection, so `updateNSView` re-checks the table each time it changes.
    var selectionToken: Int = 0

    final class Probe: NSView {
        private var observation: NSKeyValueObservation?
        private weak var observedTable: NSTableView?

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
                    if table !== observedTable {
                        observedTable = table
                        observation = Self.keepSilenced(table)
                    } else if table.selectionHighlightStyle != .none {
                        table.selectionHighlightStyle = .none
                    }
                    return
                }
                node = current.superview
            }
        }

        /// Sets the table's selection highlight to `.none` and keeps it there: whatever sets it back is undone at
        /// once. The returned observation must be kept alive.
        static func keepSilenced(_ table: NSTableView) -> NSKeyValueObservation {
            table.selectionHighlightStyle = .none
            return table.observe(\.selectionHighlightStyle, options: [.new]) { table, _ in
                MainActor.assumeIsolated {
                    if table.selectionHighlightStyle != .none { table.selectionHighlightStyle = .none }
                }
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
