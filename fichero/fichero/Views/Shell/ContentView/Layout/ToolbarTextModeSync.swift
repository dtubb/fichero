#if os(macOS)
import AppKit
import SwiftUI

/// The bars' labels FOLLOW the window toolbar's own text mode (Daniel,
/// 2026-08-31: "when the top toolbar has show text on, they should also show
/// text"). The toolbar's Icon/Icon-and-Text choice is AppKit state with no
/// SwiftUI seam, so a zero-size representable watches it via KVO and writes
/// the shared labels flag both bars already read.
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
#endif
