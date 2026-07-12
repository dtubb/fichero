// swiftlint:disable file_length
import SwiftUI

/// Distraction-free full-window reading (#2520): black background, just the
/// page, with controls that auto-reveal on mouse movement and fade away.
///
/// Folds onto the existing reader stack — the page is a `DocumentCanvas`, so
/// zoom / pan / loupe and storage-HTTP image loading come for free (no parallel
/// viewer, never a local path). Presented as a top-level overlay over the whole
/// window, so the sidebar, inspector, and toolbar are all hidden behind it.
/// A loaded translation representation of the current page (#3329): the target
/// language code + the translated text (from a `translation` artifact whose
/// `data.target_lang` records the language).
struct TranslationRep: Identifiable {
    let lang: String
    let content: String
    /// Provenance (#3325 step 4): the model that produced it, and whether a
    /// human has reviewed it.
    let provider: String?
    let model: String?
    let reviewed: Bool
    var id: String { lang }
    /// Human name, e.g. "Spanish" for "es"; falls back to the raw code.
    var displayName: String {
        Locale.current.localizedString(forLanguageCode: lang)?.capitalized
            ?? lang.uppercased()
    }
    /// One-line provenance: "provider · model", omitting blanks.
    var provenance: String {
        [provider, model].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
    }
}

// swiftlint:disable:next type_body_length
struct ImmersiveReaderView: View {
    let document: Document
    @Binding var isPresented: Bool
    /// Sibling page/image documents for prev/next, in display order.
    var siblings: [Document] = []
    var onNavigate: ((Document) -> Void)?

    @Environment(WindowState.self) private var windowState
    /// Reduce-motion falls back from the page-turn to a plain crossfade (#2485).
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// Reading-mark store for the immersive star/bookmark (#3548). Optional so
    /// the full-screen reader is safe if a host doesn't inject it.
    @Environment(AnnotationStore.self) private var annotationStore: AnnotationStore?
    /// Transient confirmation after a page mark is saved.
    @State private var markConfirmation: String?

    /// Optional page-curl-style turn animation when paging (#2485). On by
    /// default (Daniel: "books has page curls I like"); a fast non-animated mode
    /// is the toggle off. Persists per the @AppStorage key across launches.
    @AppStorage("reader.pageTurnAnimated") private var pageTurnAnimated = true
    /// Direction of the last page turn, captured in `navigate` before the parent
    /// swaps `document`, so the transition that plays on the re-render curls the
    /// right way (forward = turning to the next page).
    @State private var turnForward = true

    @State private var controlsVisible = true
    @State private var hideTask: Task<Void, Never>?
    /// Loaded translations for the current page, one per language (#3329).
    @State private var translations: [TranslationRep] = []
    /// Per-window: which representation the reader shows — "source",
    /// "diplomatic", or "lang:<code>" (#3325 reader slice / #3329).
    @SceneStorage("reader.representation") private var representationKey: String = "source"

    /// The canvas content for the chosen representation. Source is the storage
    /// page image; Diplomatic is the raw page_content; a `lang:xx` key shows that
    /// language's translation. All reuse existing DocumentCanvas cases — no
    /// parallel view. Falls back to Source if a selected translation is gone.
    private var canvasContent: DocumentCanvas.Content {
        if representationKey == "diplomatic" {
            return .markdown(text: document.pageContent ?? "")
        }
        if representationKey.hasPrefix("lang:") {
            let lang = String(representationKey.dropFirst("lang:".count))
            if let translation = translations.first(where: { $0.lang == lang }) {
                return .markdown(text: translation.content)
            }
        }
        return .imageStorageDisplay(documentId: document.id)
    }

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
        .task(id: document.id) { await loadTranslations() }
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

    private var controlsOverlay: some View {
        VStack {
            HStack {
                // Source (page image) / Diplomatic (page_content) / one per
                // translated language (#3325 reader slice, #3329). Dynamic, so a
                // Menu rather than a fixed segmented control.
                Menu {
                    Button { representationKey = "source" } label: {
                        Label("Source", systemImage: "photo")
                    }
                    Button { representationKey = "diplomatic" } label: {
                        Label("Diplomatic", systemImage: "text.alignleft")
                    }
                    if !translations.isEmpty {
                        Divider()
                        Section("Translations") {
                            ForEach(translations) { translation in
                                Button(translation.displayName) {
                                    representationKey = "lang:\(translation.lang)"
                                }
                            }
                        }
                    }
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "character.book.closed")
                        Text(currentRepresentationLabel)
                    }
                    .foregroundStyle(.white)
                    .padding(.horizontal, 12)
                    .padding(.vertical, 6)
                    .background(.ultraThinMaterial, in: Capsule())
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("Switch the reader between the page image, transcript, and translations")

                provenanceCaption

                Spacer()
                Button(action: exit) {
                    Image(systemName: "xmark")
                        .font(.title3.weight(.semibold))
                        .foregroundStyle(.white)
                        .padding(10)
                        .background(.ultraThinMaterial, in: Circle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Exit full screen reader")
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
                .accessibilityLabel("Previous page")

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
                .accessibilityLabel("Next page")

                // Reading-mark palette (#2516 / #3548): star + bookmark the
                // current page without leaving full screen.
                Divider().frame(height: 16).overlay(Color.white.opacity(0.3))

                Button {
                    markCurrentPage(kind: .rating, label: "Starred")
                } label: {
                    Image(systemName: "star")
                }
                .disabled(annotationStore == nil)
                .accessibilityLabel("Star this page")
                .help("Star this page as a reading mark")

                Button {
                    markCurrentPage(kind: .bookmark, label: "Bookmarked")
                } label: {
                    Image(systemName: "bookmark")
                }
                .disabled(annotationStore == nil)
                .accessibilityLabel("Bookmark this page")
                .help("Bookmark this page")
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

    /// The translation currently being viewed, if the selection is a language.
    private var currentTranslation: TranslationRep? {
        guard representationKey.hasPrefix("lang:") else { return nil }
        let lang = String(representationKey.dropFirst("lang:".count))
        return translations.first { $0.lang == lang }
    }

    /// Provenance + AI badge for the shown representation (#3325 step 4). Only a
    /// translation is a derived AI representation here — Source/Diplomatic aren't.
    @ViewBuilder
    private var provenanceCaption: some View {
        if let translation = currentTranslation {
            HStack(spacing: 6) {
                if !translation.reviewed {
                    Image(systemName: "sparkles").foregroundStyle(.purple)
                }
                Text(translation.reviewed ? "Translation" : "AI translation · unreviewed")
                if !translation.provenance.isEmpty {
                    Text("· \(translation.provenance)").foregroundStyle(.white.opacity(0.7))
                }
            }
            .font(.caption)
            .foregroundStyle(.white)
            .padding(.horizontal, 10)
            .padding(.vertical, 5)
            .background(.ultraThinMaterial, in: Capsule())
            .help("This representation is an AI-generated translation; review before citing.")
        }
    }

    private var currentRepresentationLabel: String {
        if representationKey == "diplomatic" { return "Diplomatic" }
        if representationKey.hasPrefix("lang:") {
            let lang = String(representationKey.dropFirst("lang:".count))
            return translations.first(where: { $0.lang == lang })?.displayName
                ?? (Locale.current.localizedString(forLanguageCode: lang)?.capitalized ?? lang.uppercased())
        }
        return "Source"
    }

    /// Fetch the current page's `translation` artifacts and index them by
    /// language (#3329). One entry per language (first wins). Reaches the service
    /// via the window's library (the reader isn't in the artifact-service
    /// environment). If the persisted selection points at a language that's no
    /// longer present, fall back to Source.
    private func loadTranslations() async {
        guard let service = LibraryManager.shared.getLibrary(id: windowState.libraryId)?.artifactService else {
            translations = []
            return
        }
        do {
            let artifacts = try await service.getArtifacts(forDocumentId: document.id, type: "translation")
            var seen = Set<String>()
            translations = artifacts.compactMap { artifact -> TranslationRep? in
                guard let data = artifact.data,
                      let lang = data["target_lang"]?.value as? String,
                      let content = artifact.content,
                      seen.insert(lang).inserted else { return nil }
                return TranslationRep(
                    lang: lang,
                    content: content,
                    provider: artifact.provider,
                    model: artifact.model,
                    reviewed: artifact.reviewed
                )
            }
        } catch {
            translations = []
        }
        if representationKey.hasPrefix("lang:") {
            let lang = String(representationKey.dropFirst("lang:".count))
            if !translations.contains(where: { $0.lang == lang }) {
                representationKey = "source"
            }
        }
    }

    /// Add a page-scoped reading mark (star / bookmark) for the current page
    /// without leaving full screen (#3548). Page-anchored, so it persists as a
    /// reading mark in the Notes layer regardless of re-layout.
    private func markCurrentPage(kind: AnnotationKind, label: String) {
        guard let store = annotationStore else { return }
        Task {
            _ = await store.addNote(scope: .page(document.id), text: "", kind: kind)
            markConfirmation = label
            revealControls()
            try? await Task.sleep(for: .seconds(1.5))
            if markConfirmation == label { markConfirmation = nil }
        }
    }

    private func navigate(by offset: Int) {
        guard let index = siblingIndex else { return }
        let target = index + offset
        guard siblings.indices.contains(target) else { return }
        // Capture the turn direction BEFORE the parent swaps `document` so the
        // transition on the next render curls the right way (#2485).
        turnForward = offset > 0
        onNavigate?(siblings[target])
        revealControls()
    }

    /// The page-turn transition for a prev/next swap. Off ⇒ no visual transition
    /// (fast mode); reduce-motion ⇒ a plain crossfade; otherwise a 3D page-turn
    /// hinged on the spine edge (leading when going forward). (#2485)
    private var pageTurnTransition: AnyTransition {
        guard pageTurnAnimated else { return .identity }
        guard !reduceMotion else { return .opacity }
        return .pageTurn(forward: turnForward)
    }

    /// Animation timing paired with `pageTurnTransition`. Nil ⇒ instant swap
    /// (fast mode); shorter under reduce-motion.
    private var pageTurnAnimation: Animation? {
        guard pageTurnAnimated else { return nil }
        return .easeInOut(duration: reduceMotion ? 0.2 : 0.45)
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

// MARK: - Page-turn transition (#2485)

/// A book-style page-turn: the page rotates in 3D around its spine edge with a
/// little perspective, so paging reads like turning a page rather than a hard
/// cut. Reusable across the reading surfaces (the folder-image reader here; the
/// PDF/Page-tab reader can adopt it once the 4-tab restructure lands and owns a
/// single page renderer). Pure SwiftUI — no Metal / CATransition / parallel
/// renderer — so it survives the restructure and needs no platform fork.
struct PageTurnModifier: ViewModifier {
    /// Rotation at the "away" end of the turn, in degrees. 0 is flat/on-screen.
    let angle: Double
    /// The hinge the page rotates around — the spine edge.
    let anchor: UnitPoint

    func body(content: Content) -> some View {
        content
            .rotation3DEffect(
                .degrees(angle),
                axis: (x: 0, y: 1, z: 0),
                anchor: anchor,
                perspective: 0.5
            )
            // Fade the swinging page so the incoming/outgoing pages cross
            // cleanly instead of both rendering opaque mid-turn.
            .opacity(angle == 0 ? 1 : 0)
    }
}

extension AnyTransition {
    /// A page-turn keyed to direction: forward hinges on the leading (spine)
    /// edge with the incoming page swinging in from the right and the outgoing
    /// page flipping left; backward mirrors it on the trailing edge. (#2485)
    static func pageTurn(forward: Bool) -> AnyTransition {
        let hinge: UnitPoint = forward ? .leading : .trailing
        let insertion = AnyTransition.modifier(
            active: PageTurnModifier(angle: forward ? -90 : 90, anchor: hinge),
            identity: PageTurnModifier(angle: 0, anchor: hinge)
        )
        let removal = AnyTransition.modifier(
            active: PageTurnModifier(angle: forward ? 90 : -90, anchor: hinge),
            identity: PageTurnModifier(angle: 0, anchor: hinge)
        )
        return .asymmetric(insertion: insertion, removal: removal)
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
