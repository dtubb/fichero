import SwiftUI

/// Distraction-free full-window reading (#2520): black background, just the
/// page, with controls that auto-reveal on mouse movement and fade away.
///
/// Folds onto the existing reader stack — the page is a `DocumentCanvas`, so
/// zoom / pan / loupe and storage-HTTP image loading come for free (no parallel
/// viewer, never a local path). Presented as a top-level overlay over the whole
/// window, so the sidebar, inspector, and toolbar are all hidden behind it.
struct ImmersiveReaderView: View {
    let document: Document
    @Binding var isPresented: Bool
    /// Sibling page/image documents for prev/next, in display order.
    var siblings: [Document] = []
    var onNavigate: ((Document) -> Void)?

    @State private var controlsVisible = true
    @State private var hideTask: Task<Void, Never>?

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            DocumentCanvas(content: .imageStorageDisplay(documentId: document.id))
                .ignoresSafeArea()

            if controlsVisible {
                controlsOverlay
                    .transition(.opacity)
            }
        }
        .background(KeyboardExitCatcher { exit() })
        .onContinuousHover { phase in
            switch phase {
            case .active:
                revealControls()
            case .ended:
                break
            }
        }
        .onExitCommand(perform: exit)
    }

    private var controlsOverlay: some View {
        VStack {
            HStack {
                Spacer()
                Button(action: exit) {
                    Image(systemName: "xmark")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(10)
                        .background(.ultraThinMaterial, in: Circle())
                }
                .buttonStyle(.plain)
                .keyboardShortcut(.cancelAction)
                .help("Exit full screen (Esc)")
            }
            .padding(16)

            Spacer()

            // Bottom control bar — page navigation + title. Auto-hides with the
            // rest of the chrome. A thumbnail filmstrip + annotation palette
            // graft on here next (#2516).
            HStack(spacing: 16) {
                Button {
                    navigate(by: -1)
                } label: {
                    Image(systemName: "chevron.left")
                }
                .disabled(siblingIndex == nil || siblingIndex == 0)

                Text(document.name)
                    .font(.callout)
                    .foregroundStyle(.white)
                    .lineLimit(1)

                Button {
                    navigate(by: 1)
                } label: {
                    Image(systemName: "chevron.right")
                }
                .disabled(siblingIndex == nil || siblingIndex == siblings.count - 1)
            }
            .buttonStyle(.plain)
            .foregroundStyle(.white)
            .padding(.horizontal, 20)
            .padding(.vertical, 10)
            .background(.ultraThinMaterial, in: Capsule())
            .padding(.bottom, 24)
        }
    }

    private var siblingIndex: Int? {
        siblings.firstIndex { $0.id == document.id }
    }

    private func navigate(by offset: Int) {
        guard let index = siblingIndex else { return }
        let target = index + offset
        guard siblings.indices.contains(target) else { return }
        onNavigate?(siblings[target])
        revealControls()
    }

    private func revealControls() {
        if !controlsVisible {
            withAnimation(.easeInOut(duration: 0.15)) { controlsVisible = true }
        }
        hideTask?.cancel()
        hideTask = Task { @MainActor in
            try? await Task.sleep(for: .seconds(2.5))
            guard !Task.isCancelled else { return }
            withAnimation(.easeInOut(duration: 0.4)) { controlsVisible = false }
        }
    }

    private func exit() {
        hideTask?.cancel()
        isPresented = false
    }
}

#if canImport(AppKit)
import AppKit

/// Hosts a first responder so the immersive overlay reliably receives the Esc
/// key even before the user interacts (`onExitCommand` needs focus). Invisible.
private struct KeyboardExitCatcher: NSViewRepresentable {
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
private struct KeyboardExitCatcher: View {
    let onExit: () -> Void
    var body: some View { Color.clear }
}
#endif
