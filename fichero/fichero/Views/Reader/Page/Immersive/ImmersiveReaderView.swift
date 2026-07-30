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

    @Environment(WindowState.self) var windowState
    /// Reduce-motion falls back from the page-turn to a plain crossfade (#2485).
    @Environment(\.accessibilityReduceMotion) var reduceMotion
    /// Reading-mark store for the immersive star/bookmark (#3548). Optional so
    /// the full-screen reader is safe if a host doesn't inject it.
    @Environment(AnnotationStore.self) var annotationStore: AnnotationStore?
    /// Transient confirmation after a page mark is saved.
    @State var markConfirmation: String?

    /// Optional page-curl-style turn animation when paging (#2485). On by
    /// default (the maintainer: "books has page curls I like"); a fast non-animated mode
    /// is the toggle off. Persists per the @AppStorage key across launches.
    @AppStorage("reader.pageTurnAnimated") var pageTurnAnimated = true
    /// Direction of the last page turn, captured in `navigate` before the parent
    /// swaps `document`, so the transition that plays on the re-render curls the
    /// right way (forward = turning to the next page).
    @State var turnForward = true

    @State var controlsVisible = true
    @State var hideTask: Task<Void, Never>?
    /// Loaded translations for the current page, one per language (#3329).
    @State var translations: [TranslationRep] = []
    /// Model-generated conversion renditions of this page (#4329) — newest per
    /// format (Markdown / HTML / SVG), switchable in place like translations.
    @State var renditions: [Artifact] = []
    /// Per-window: which representation the reader shows — "source",
    /// "diplomatic", or "lang:<code>" (#3325 reader slice / #3329).
    @SceneStorage("reader.representation") var representationKey: String = "source"

    var body: some View {
        ZStack {
            Color.black.ignoresSafeArea()

            // Keying the canvas on the page id makes a prev/next navigation a
            // view-identity swap, which the page-turn transition animates. A
            // representation change (Source/Diplomatic/translation) keeps the
            // same id, so it updates in place with no turn. (#2485)
            DocumentCanvas(content: canvasContent)
                .ignoresSafeArea()
                .id(document.id)
                .transition(pageTurnTransition)
                .animation(pageTurnAnimation, value: document.id)

            if controlsVisible {
                controlsOverlay
                    .transition(.opacity)
            }

            if let markConfirmation {
                Text(markConfirmation)
                    .font(.callout.weight(.semibold))
                    .foregroundStyle(.white)
                    .padding(.horizontal, 16)
                    .padding(.vertical, 10)
                    .background(.ultraThinMaterial, in: Capsule())
                    .transition(.opacity)
                    .allowsHitTesting(false)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: markConfirmation)
        .background(KeyboardExitCatcher { exit() })
        .task(id: document.id) {
            await loadTranslations()
            await loadRenditions()
        }
        .onContinuousHover { phase in
            switch phase {
            case .active:
                revealControls()
            case .ended:
                break
            }
        }
        #if os(macOS)
        .onExitCommand(perform: exit)
        #endif
    }
}
