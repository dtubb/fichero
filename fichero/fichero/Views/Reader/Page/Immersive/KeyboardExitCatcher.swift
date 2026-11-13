import SwiftUI

#if canImport(AppKit)
import AppKit

/// Which way a key turns the full-screen page (#6560): ← the previous page, → the next, with no modifier (⌘← and the
/// like stay the system's); nil for any other key.
enum KeyboardPageStep {
    static func step(keyCode: UInt16, modifiers: NSEvent.ModifierFlags) -> Int? {
        guard modifiers.isDisjoint(with: [.command, .option, .control, .shift]) else { return nil }
        switch keyCode {
        case 123: return -1  // ←
        case 124: return 1  // →
        default: return nil
        }
    }
}

/// Hosts a first responder so the immersive overlay reliably receives the Esc
/// key even before the user interacts (`onExitCommand` needs focus). Invisible.
/// ← and → turn the page (`onPage(-1)` / `onPage(1)`, #6560), with the controls faded or not.
struct KeyboardExitCatcher: NSViewRepresentable {
    let onExit: () -> Void
    var onPage: ((Int) -> Void)?

    func makeNSView(context: Context) -> NSView {
        let view = ExitCatchingView()
        view.onExit = onExit
        view.onPage = onPage
        DispatchQueue.main.async { view.window?.makeFirstResponder(view) }
        return view
    }

    func updateNSView(_ nsView: NSView, context: Context) {
        (nsView as? ExitCatchingView)?.onExit = onExit
        (nsView as? ExitCatchingView)?.onPage = onPage
    }

    private final class ExitCatchingView: NSView {
        var onExit: (() -> Void)?
        var onPage: ((Int) -> Void)?
        override var acceptsFirstResponder: Bool { true }
        override func keyDown(with event: NSEvent) {
            if event.keyCode == 53 { // Esc
                onExit?()
            } else if let step = KeyboardPageStep.step(keyCode: event.keyCode, modifiers: event.modifierFlags), let onPage {
                onPage(step)
            } else {
                super.keyDown(with: event)
            }
        }
    }
}
#else
struct KeyboardExitCatcher: View {
    let onExit: () -> Void
    var onPage: ((Int) -> Void)?
    var body: some View { Color.clear }
}
#endif
