import SwiftUI

#if canImport(AppKit)
import AppKit

/// Hosts a first responder so the immersive overlay reliably receives the Esc
/// key even before the user interacts (`onExitCommand` needs focus). Invisible.
struct KeyboardExitCatcher: NSViewRepresentable {
    let onExit: () -> Void

    func makeNSView(context: Context) -> NSView {
        let view = ExitCatchingView()
        view.onExit = onExit
        DispatchQueue.main.async { view.window?.makeFirstResponder(view) }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        (nsView as? ExitCatchingView)?.onExit = onExit
    }

    private final class ExitCatchingView: NSView {
        var onExit: (() -> Void)?
        override var acceptsFirstResponder: Bool { true }
        override func keyDown(with event: NSEvent) {
            if event.keyCode == 53 { // Esc
                onExit?()
            } else {
                super.keyDown(with: event)
            }
        }
    }
}
#else
struct KeyboardExitCatcher: View {
    let onExit: () -> Void
    var body: some View { Color.clear }
}
#endif
