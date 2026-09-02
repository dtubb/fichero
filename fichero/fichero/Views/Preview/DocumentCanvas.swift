import PDFKit
import SwiftUI

/// One canonical canvas for image and PDF documents (#1402).
///
/// Replaces the three parallel zoom wrappers (ZoomableImageView, and the
/// since-removed ZoomableNSImageView) with a single entry point that reuses
/// the existing viewer stack:
///   • image storage      → StorageDisplayImageCanvas — full loupe/zoom/magnifier via HTTP
///   • image rendered     → ZoomableImagePreview(renderedImage:) — same stack, NSImage override
///   • PDF                → PDFPageWithToolbar
///
/// Plain preview, folder-page reading surface, and the editor all route here.
struct DocumentCanvas: View {
    let content: Content
    /// Fired when the user navigates to a different PDF page within the canvas.
    var onPageIndexChange: ((Int) -> Void)?
    /// Fired when the user steps to a sibling image in the folder image viewer.
    var onNavigateToDocument: ((String) -> Void)?
    /// Drives the image reader toolbar's edit button. `nil` greys the tool out
    /// (e.g. PDFs, which have no in-app editor). Threaded down to the image
    /// viewer so the edit control lives in the bottom reader toolbar instead of
    /// floating over the split control (#2421).
    var isEditing: Binding<Bool>?
    /// Extra normalized `[x,y,w,h]` boxes drawn over an image canvas — the
    /// entry-source highlight (preview-layers M1, #27). Display-only; the
    /// annotation region layer is unaffected.
    var highlightBoxes: [[Double]] = []
    /// Entry ladder (2026-08-23): open zoomed to this normalized rect, and
    /// route vertical steps to the host's containment ladder. Image canvases
    /// only; other content kinds ignore both.
    var focusRegion: [Double]?
    var onContainmentStep: ((Int) -> Bool)?

    enum Content {
        /// A backend storage display image, resolved by document id.
        case imageStorageDisplay(documentId: String)
        /// A backend-rendered PlatformImage (editor mode — may be nil while
        /// loading). `renditionId` names the rendition those pixels ARE when
        /// the preferred-first path fetched them (2026-08-24) — the preview
        /// then lands its flip index there without re-fetching.
        case imageRendered(image: PlatformImage?, documentId: String, renditionId: String? = nil)
        /// A PDF document at a given page index.
        case pdf(documentId: String, pageIndex: Int)
        /// A text/Markdown representation (#2264) — e.g. a `convert` artifact.
        case markdown(text: String)
        /// A model-generated HTML rendition of the page (#4329), WebKit-rendered.
        case html(content: String)
        /// A model-generated SVG rendition of the page (#4329), WebKit-rendered.
        case svg(content: String)
    }

    /// The canvas content for a `conversion` artifact, routed by its stamped
    /// `target_format` (falling back to sniffing the markup) — so a rendition
    /// renders, never shows raw source (#4329).
    static func renditionContent(for artifact: Artifact) -> Content {
        let text = artifact.content ?? ""
        let format = (artifact.data?["target_format"]?.value as? String)
            ?? Self.sniffRenditionFormat(text)
        switch format {
        case "svg": return .svg(content: text)
        case "html": return .html(content: text)
        default: return .markdown(text: text)
        }
    }

    /// Best-effort format sniff for legacy conversion artifacts saved before
    /// the `target_format` stamp existed.
    static func sniffRenditionFormat(_ text: String) -> String {
        let head = text.trimmingCharacters(in: .whitespacesAndNewlines)
            .prefix(500)
            .lowercased()
        if head.contains("<svg") { return "svg" }
        if head.hasPrefix("<!doctype html") || head.contains("<html") { return "html" }
        return "markdown"
    }

    var body: some View {
        switch content {
        case .imageStorageDisplay(let docId):
            StorageDisplayImageCanvas(
                documentId: docId,
                onNavigateToDocument: onNavigateToDocument,
                isEditing: isEditing,
                highlightBoxes: highlightBoxes,
                focusRegion: focusRegion,
                onContainmentStep: onContainmentStep
            )
        case .imageRendered(let nsImage, let docId, let renditionId):
            #if os(macOS)
            ZoomableImagePreview(
                documentId: docId,
                renderedImage: nsImage,
                renderedRenditionId: renditionId,
                onNavigateToDocument: onNavigateToDocument,
                isEditing: isEditing,
                highlightBoxes: highlightBoxes,
                focusRegion: focusRegion,
                onContainmentStep: onContainmentStep
            )
            #else
            // The iOS preview has no rendition-flip state (macOS-only today),
            // so it takes the rendered image without the rendition id.
            // swiftlint:disable:next redundant_discardable_let
            let _ = renditionId
            ZoomableImagePreview(
                documentId: docId,
                renderedImage: nsImage,
                onNavigateToDocument: onNavigateToDocument,
                isEditing: isEditing,
                highlightBoxes: highlightBoxes,
                focusRegion: focusRegion,
                onContainmentStep: onContainmentStep
            )
            #endif
        case .pdf(let documentId, let pageIndex):
            PDFPageWithToolbar(
                documentId: documentId,
                pageIndex: pageIndex,
                onPageIndexChange: onPageIndexChange
            )
        case .markdown(let text):
            MarkdownCanvas(text: text)
        case .html(let content):
            WebContentCanvas(content: content, kind: .html)
        case .svg(let content):
            WebContentCanvas(content: content, kind: .svg)
        }
    }
}

/// Renders a Markdown representation as scrollable, selectable text (#2264).
///
/// Native rendering only — `AttributedString(markdown:)` for inline + block
/// syntax, falling back to the raw text if it doesn't parse. Heavier Markdown
/// (tables, images) can graduate to a web view later if a corpus needs it.
private struct MarkdownCanvas: View {
    let text: String

    private var attributed: AttributedString {
        (try? AttributedString(
            markdown: text,
            options: .init(interpretedSyntax: .inlineOnlyPreservingWhitespace)
        )) ?? AttributedString(text)
    }

    var body: some View {
        ScrollView {
            Text(attributed)
                .font(.body)
                .textSelection(.enabled)
                .frame(maxWidth: .infinity, alignment: .leading)
                // Slim margin — more width for the text (Daniel, 2026-08-10).
                .padding(8)
        }
    }
}

private struct StorageDisplayImageCanvas: View {
    let documentId: String
    var onNavigateToDocument: ((String) -> Void)?
    var isEditing: Binding<Bool>?
    var highlightBoxes: [[Double]] = []
    var focusRegion: [Double]?
    var onContainmentStep: ((Int) -> Bool)?

    @Environment(StorageService.self) private var storageService
    /// Optional: hosts without a store (isolated previews) skip the
    /// grant-prompt path; the degraded-thumbnail capsule still renders.
    @Environment(DocumentStore.self) private var documentStore: DocumentStore?
    @Environment(RenditionService.self) private var renditionService: RenditionService?
    @State private var image: PlatformImage?
    /// The rendition whose pixels `image` holds, when the preferred-first
    /// path won — handed down so the preview does NOT re-fetch them.
    @State private var renderedRenditionId: String?
    @State private var loadError: Error?
    /// Monotonic token: each load claims a generation and only the latest may
    /// publish. Guards the rapid page-flip race — an older page's slower fetch
    /// must not land AFTER the current page's image and replace it.
    @State private var loadGeneration = 0

    var body: some View {
        VStack(spacing: 0) {
            interimContent
            // The reader toolbar mounts inside ZoomableImagePreview only once
            // the display image exists — every earlier frame (thumbnail,
            // skeleton, error) had NO bottom bar, so the bar "flipped in" when
            // the original arrived (Daniel, 2026-08-23). An inert ReaderToolbar
            // of identical geometry holds the bottom edge until then; the real
            // one replaces it in place with no jump.
            if image == nil {
                Divider()
                // Quiet style, matching the real bar's geometry (Daniel,
                // 2026-08-29 restructure) — the placeholder must hold the
                // same bottom edge the live quiet bar occupies.
                ReaderToolbar(
                    style: .quiet,
                    pageNav: nil,
                    scalePercent: 100,
                    zoomIn: {}, zoomOut: {}, fitToWindow: {}, actualSize: {}
                )
                .disabled(true)
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        // Cross-fade the branch swap as the loaded image replaces the skeleton.
        .animation(FrameAnimation.crossfade, value: image == nil)
        .task(id: documentId) { await loadImage() }
    }

    @ViewBuilder
    private var interimContent: some View {
        ZStack {
            if image != nil {
                DocumentCanvas(
                    content: .imageRendered(
                        image: image,
                        documentId: documentId,
                        renditionId: renderedRenditionId
                    ),
                    onNavigateToDocument: onNavigateToDocument,
                    isEditing: isEditing,
                    highlightBoxes: highlightBoxes,
                    focusRegion: focusRegion,
                    onContainmentStep: onContainmentStep
                )
            } else if let loadError {
                if let thumbnail = storageService.cachedThumbnail(for: documentId) {
                    // Degrade to the THUMBNAIL, not a dead pane (user,
                    // 2026-08-20: "just load the thumbnail, and if you can't
                    // find the original, flag it briefly — the user can keep
                    // working"). The failure stays visible as a compact
                    // banner with the retry, never a full-pane stop.
                    thumbnail
                        .resizable()
                        .aspectRatio(contentMode: .fit)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        // TOP, not bottom (Daniel, 2026-08-20: "the showing
                        // thumbnails replaces the bottom bar — that's not
                        // good"): the pane's mini toolbar owns the bottom
                        // edge, and the capsule was sitting on top of it.
                        .overlay(alignment: .top) {
                            HStack(spacing: 8) {
                                Image(systemName: "exclamationmark.triangle")
                                Text("Showing thumbnail — original unavailable")
                                    .font(.caption)
                                Button("Retry") { retryOriginal() }
                                    .controlSize(.small)
                            }
                            .padding(.horizontal, 12)
                            .padding(.vertical, 6)
                            .background(.regularMaterial, in: Capsule())
                            .padding(.top, 10)
                            .help(loadError.localizedDescription)
                        }
                } else {
                    // No fallback pixels at all: surface the failure with a
                    // message + Retry instead of a mute icon (#3210).
                    ContentUnavailableView {
                        Label("Couldn't load image", systemImage: "photo")
                    } description: {
                        Text(loadError.localizedDescription)
                    } actions: {
                        Button("Retry") { retryOriginal() }
                    }
                }
            } else if let thumbnail = storageService.cachedThumbnail(for: documentId) {
                // #4583 (Daniel: "I click on one image and it takes a moment
                // to load in"): the grid already fetched this document's
                // thumbnail — show it at fit IMMEDIATELY and let the
                // display-quality image replace it in place. No blank beat.
                thumbnail
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                // ★ EVERY FRAME PERFECT (#3616): a sized skeleton filling the
                // reserved pane instead of a bare spinner, so the image/PDF page
                // cross-fades in (below) with no blank frame or pop.
                SkeletonPlaceholder()
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func loadImage() async {
        // ★ EVERY FRAME PERFECT (#18/#113 page-turn flash): do NOT nil the
        // current image while the next page loads. Nil-first meant every page
        // flip dropped to the white skeleton for the fetch+decode window; the
        // previous page now stays up and the new one replaces it in place
        // (instant on a cache/prefetch hit). The skeleton still shows on
        // FIRST load, when there is nothing older to hold.
        loadGeneration += 1
        let claimed = loadGeneration
        loadError = nil
        // Bounded retry (2026-09-02, search-results 404): the storage
        // endpoints GENERATE a missing rendition on request, but shed a
        // transient 404 when the generation semaphore is saturated — the
        // normal state right after an import, and exactly when search
        // results show fresh documents. Two quiet retries with backoff
        // absorb the shed; a real failure still surfaces, once.
        for attempt in 0 ..< 3 {
            do {
                try await loadImageOnce(claimed: claimed)
                return
            } catch {
                guard claimed == loadGeneration else { return }
                if attempt < 2, Self.isTransientStorageMiss(error) {
                    try? await Task.sleep(for: .milliseconds(600 * (attempt + 1)))
                    continue
                }
                // A failed load must not silently keep showing the WRONG page.
                image = nil
                loadError = error
                promptForSourceAccessIfMissing()
                return
            }
        }
    }

    /// A shed 404 from the storage endpoints ("no thumbnail/display image
    /// generated yet") — worth a quiet retry; anything else is not.
    static func isTransientStorageMiss(_ error: Error) -> Bool {
        let text = String(describing: error).lowercased()
        return text.contains("404") || text.contains("not found")
            || text.contains("no thumbnail")
    }

    private func loadImageOnce(claimed: Int) async throws {
        do {
            // PREFERRED RENDITION FIRST (Daniel, 2026-08-24: "it should just
            // load background removed"): a sibling step used to fetch the
            // base display image, show it, and THEN the preview fetched the
            // sticky rendition and swapped again — three images per swipe.
            // Resolve the preference before any pixel fetch; the base
            // display is now the FALLBACK, not a step.
            if let renditionService {
                _ = await renditionService.load(documentId: documentId)
                let displayable = renditionService.displayable(documentId: documentId)
                // Rendition flip (sticky preference) is macOS-only today; iOS
                // always takes the engine's primary via the base display path,
                // so the whole preferred-fetch branch compiles out there — the
                // iOS build's `preferred = 0` constant made it provably dead
                // and Xcode 27 said so ("will never be executed").
                #if os(macOS)
                let sticky = UserDefaults.standard.string(
                    forKey: ZoomableImagePreview.stickyRenditionRoleKey
                )
                let preferred = preferredRenditionIndex(in: displayable, stickyRole: sticky)
                // Index 0 is the engine's primary — the base display image
                // serves that (cheaper, cached). Only a preferred FLIP
                // target is worth the rendition fetch here.
                if preferred != 0, displayable.indices.contains(preferred) {
                    let target = displayable[preferred]
                    let data = try await renditionService.contentData(
                        documentId: documentId, renditionId: target.id
                    )
                    if let loaded = PlatformImage(data: data) {
                        guard claimed == loadGeneration else { return }
                        image = loaded
                        renderedRenditionId = target.id
                        return
                    }
                }
                #else
                _ = displayable
                #endif
            }
            let loaded = try await storageService.getDisplayPlatformImage(documentId)
            guard claimed == loadGeneration else { return }  // a newer flip won
            image = loaded
            renderedRenditionId = nil
        } catch {
            // The retry loop in loadImage owns failure handling.
            throw error
        }
    }

    /// A display 404 for a linked source usually means the sandboxed engine
    /// has no grant for the source's folder ("No source found",
    /// has_bookmark=False) — so ask for it RIGHT HERE instead of leaving the
    /// user to discover File ▸ Grant Folder Access… (user, 2026-08-21:
    /// "can't we ask for folder access directly if it's needed?"). At most
    /// one panel per folder per run; a fresh grant reaches the running
    /// engine, so the retry succeeds without a relaunch.
    private func promptForSourceAccessIfMissing() {
        promptForSourceAccess(force: false)
    }

    /// The banner's Retry: an explicit click always offers the folder picker
    /// when access is missing (bypassing the once-per-folder prompt guard),
    /// then reloads — with access already in hand it just reloads.
    func retryOriginal() {
        promptForSourceAccess(force: true)
        Task { await loadImage() }
    }

    private func promptForSourceAccess(force: Bool) {
        #if os(macOS)
        guard let store = documentStore else { return }
        let candidates = store.currentDocuments
            + store.collections
            + [store.selectedDocument].compactMap { $0 }
        guard let sourcePath = candidates.first(where: { $0.id == documentId })?.path,
              !sourcePath.isEmpty else { return }
        FolderAccessManager.shared.promptForSource(path: sourcePath, force: force) { granted in
            guard granted else { return }
            Task { await loadImage() }
        }
        #endif
    }
}
