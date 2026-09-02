import SwiftUI

#if os(macOS)
import AppKit

/// The bars' labels and the window toolbar's own text mode are ONE setting
/// (Daniel, 2026-08-31: "when the top toolbar has show text on, they should
/// also show text"; 2026-09-02: the bars' own right-click Show/Hide Labels
/// "should drive the same setting"). The toolbar's Icon/Icon-and-Text choice
/// is AppKit state with no SwiftUI seam, so a zero-size representable bridges
/// it in BOTH directions: KVO pulls the toolbar's mode into the shared labels
/// flag both bars read, and a write to that flag — which is all the bars'
/// context menu does — pushes back onto the toolbar.
///
/// The two directions cannot chase each other: each side writes only when it
/// actually disagrees with the other, so the second hop is always a no-op.
struct ToolbarTextModeSync: NSViewRepresentable {
    @Binding var showsLabels: Bool

    func makeNSView(context: Context) -> NSView {
        let view = NSView(frame: .zero)
        // The window (and its toolbar) exist only after mount.
        DispatchQueue.main.async { [weak view] in
            context.coordinator.attach(to: view?.window?.toolbar) { labelled in
                if showsLabels != labelled { showsLabels = labelled }
            }
        }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        // Re-attach if the window changed (tab moves between windows).
        context.coordinator.attach(to: nsView.window?.toolbar) { labelled in
            if showsLabels != labelled { showsLabels = labelled }
        }
        // The PUSH half: the bars' context menu wrote the flag, so the window
        // toolbar follows it. `attach` returns immediately when it is already
        // watching this toolbar, so this does not fight the pull above.
        context.coordinator.apply(showsLabels: showsLabels)
    }

    func makeCoordinator() -> Coordinator { Coordinator() }

    @MainActor
    final class Coordinator: NSObject {
        private weak var observedToolbar: NSToolbar?
        private var onChange: ((Bool) -> Void)?
        private nonisolated static let keyPath = "displayMode"

        func attach(to toolbar: NSToolbar?, onChange: @escaping (Bool) -> Void) {
            guard let toolbar, toolbar !== observedToolbar else { return }
            observedToolbar?.removeObserver(self, forKeyPath: Self.keyPath)
            observedToolbar = toolbar
            self.onChange = onChange
            onChange(toolbar.displayMode != .iconOnly)
            // String KVO, not a key path: `displayMode` is main-actor
            // isolated and Swift 6 refuses `\.displayMode`. ponytail: the
            // property is KVO-compliant in practice but undocumented; if a
            // macOS release breaks it the bars stop following until relaunch.
            toolbar.addObserver(self, forKeyPath: Self.keyPath, options: [.new], context: nil)
        }

        /// Write the label choice onto the toolbar — the context menu's half
        /// of the bridge.
        ///
        /// Compares the LABELLED READING rather than the raw mode, so a user
        /// who set the toolbar to Text Only keeps it: `.labelOnly` already
        /// means "labelled", and rewriting it to `.iconAndLabel` would be this
        /// bridge quietly overruling a choice it was only asked to mirror.
        func apply(showsLabels: Bool) {
            guard let toolbar = observedToolbar else { return }
            guard (toolbar.displayMode != .iconOnly) != showsLabels else { return }
            toolbar.displayMode = showsLabels ? .iconAndLabel : .iconOnly
        }

        // swiftlint:disable:next block_based_kvo
        nonisolated override func observeValue(
            forKeyPath keyPath: String?, of object: Any?,
            change: [NSKeyValueChangeKey: Any]?, context: UnsafeMutableRawPointer?
        ) {
            guard keyPath == Self.keyPath else { return }
            MainActor.assumeIsolated {  // AppKit posts toolbar KVO on main
                guard let toolbar = observedToolbar else { return }
                onChange?(toolbar.displayMode != .iconOnly)
            }
        }

        deinit {
            observedToolbar?.removeObserver(self, forKeyPath: Self.keyPath)
        }
    }
}
#else
/// iOS/iPadOS: there is no NSToolbar text mode to mirror — the mounts in
/// ContentView+WorkflowBar stay platform-neutral and this is a no-op. The
/// bars' own Show/Hide Labels menu still works there: it writes the same
/// flag, and on iOS nothing else reads it.
struct ToolbarTextModeSync: View {
    @Binding var showsLabels: Bool
    var body: some View { EmptyView() }
}
#endif
