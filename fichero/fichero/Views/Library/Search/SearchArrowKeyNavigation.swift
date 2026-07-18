import SwiftUI

/// Pure arrow-key index math for the search-result navigator (#1843), factored
/// out of the macOS-only view modifier so it's unit-testable on any platform.
enum SearchArrowKeyIndex {
    /// The next selected index when arrowing by `delta` (±1) through `count`
    /// items from `current` (-1 = nothing selected yet). Clamped to
    /// `[0, count - 1]`; returns -1 when there are no items (nothing to select).
    static func next(from current: Int, delta: Int, count: Int) -> Int {
        guard count > 0 else { return -1 }
        return max(0, min(count - 1, current + delta))
    }
}

#if os(macOS)
import AppKit

/// Lets ↑/↓ move the search-result selection while the user keeps typing in the
/// search field (Spotlight-standard) — which pure SwiftUI can't do because the
/// `TextField` / `NSSearchField` field editor swallows the arrow keys (#1843).
///
/// A local key-down monitor (the supported way to see keys before the field
/// editor consumes them) intercepts ↑/↓ ONLY while a text field's field editor
/// is first responder — i.e. the user is typing in the search field — so lists,
/// menus, and other arrow-driven controls keep their normal behaviour. Return
/// activates the single selected result; with no selection it falls through so
/// the field's submit (run the search) still fires.
private struct ArrowKeyResultNavigator: ViewModifier {
    let itemIds: [String]
    @Binding var selection: Set<String>
    var onActivate: (() -> Void)?

    @State private var monitor: Any?

    func body(content: Content) -> some View {
        content
            .onAppear(perform: install)
            .onDisappear(perform: remove)
    }

    private func install() {
        guard monitor == nil else { return }
        monitor = NSEvent.addLocalMonitorForEvents(matching: .keyDown) { event in
            handle(event) ? nil : event
        }
    }

    private func remove() {
        if let monitor {
            NSEvent.removeMonitor(monitor)
        }
        monitor = nil
    }

    private func handle(_ event: NSEvent) -> Bool {
        // Only hijack arrows when a text field's field editor is first responder
        // (the user is typing in the search field). Otherwise let the focused
        // control handle its own arrows (lists, menus, etc.).
        guard let responder = NSApp.keyWindow?.firstResponder,
              responder is NSTextView,
              !itemIds.isEmpty else {
            return false
        }

        switch event.keyCode {
        case 125:  // down arrow
            move(by: 1)
            return true
        case 126:  // up arrow
            move(by: -1)
            return true
        case 36, 76:  // return / enter
            if selection.count == 1 {
                onActivate?()
                return true
            }
            return false  // no selection → let the field's submit run the search
        default:
            return false
        }
    }

    private func move(by delta: Int) {
        let current = selection.first.flatMap { itemIds.firstIndex(of: $0) } ?? -1
        let next = SearchArrowKeyIndex.next(from: current, delta: delta, count: itemIds.count)
        guard itemIds.indices.contains(next) else { return }
        selection = [itemIds[next]]
    }
}

extension View {
    /// Arrow-through-results while typing in the search field (#1843).
    func arrowKeyResultNavigation(
        itemIds: [String],
        selection: Binding<Set<String>>,
        onActivate: (() -> Void)? = nil
    ) -> some View {
        modifier(ArrowKeyResultNavigator(itemIds: itemIds, selection: selection, onActivate: onActivate))
    }
}
#else
extension View {
    /// No-op on non-macOS — there's no field-editor arrow-swallowing to work
    /// around, and touch platforms don't drive selection by arrow key (#1843).
    func arrowKeyResultNavigation(
        itemIds: [String],
        selection: Binding<Set<String>>,
        onActivate: (() -> Void)? = nil
    ) -> some View {
        self
    }
}
#endif
