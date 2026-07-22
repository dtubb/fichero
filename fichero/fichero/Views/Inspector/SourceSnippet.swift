import FicheroAPIClient
import SwiftUI

// MARK: - Source crop model (#2105)

/// The evidence behind any anchored record — a claim, entity mention,
/// annotation, transcribed line, or face (#2103). Either the cropped source
/// *image* (an image/PDF bbox) or the verbatim *text* span (a char range).
/// Produced by the ephemeral-crop endpoint; rendered by ``SourceSnippet``.
enum SourceCrop {
    case image(PlatformImage)
    case text(String)
}

/// What to crop — mirrors the source-navigation anchor (`bbox` / char range on
/// a document + page). One request drives every "show me the source" surface so
/// the affordance is identical everywhere (#2105: one component, many users).
struct SourceCropRequest: Equatable {
    let documentId: String
    var bbox: [Double]?
    var pageIndex: Int?
    var pageLabel: String?
    var charStart: Int?
    var charEnd: Int?

    init(
        documentId: String,
        bbox: [Double]? = nil,
        pageIndex: Int? = nil,
        pageLabel: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil
    ) {
        self.documentId = documentId
        self.bbox = bbox
        self.pageIndex = pageIndex
        self.pageLabel = pageLabel
        self.charStart = charStart
        self.charEnd = charEnd
    }

    /// Convenience: build the crop request straight from a source-navigation
    /// request so the popover and the reveal action share one anchor.
    init(_ nav: ClaimSourceNavigationRequest) {
        self.init(
            documentId: nav.documentId,
            bbox: nav.bbox,
            pageIndex: nav.pageIndex,
            pageLabel: nav.pageLabel,
            charStart: nav.charStart,
            charEnd: nav.charEnd
        )
    }
}

/// Fetches a ``SourceCrop`` for a request. The concrete implementation calls
/// the generated ephemeral-crop op (binary body); tests inject a stub. A
/// closure seam — not a service singleton — so `SourceSnippet` stays
/// context-agnostic and reusable beyond the DocumentInspector (#3454).
typealias SourceCropFetch = @MainActor (SourceCropRequest) async throws -> SourceCrop?

// MARK: - Loader

/// Drives the snippet's async load as an observable phase machine so the view
/// updates one region in place (no wholesale re-render).
@Observable
@MainActor
final class SourceSnippetLoader {
    enum Phase {
        case idle
        case loading
        case loaded(SourceCrop)
        case empty
        case failed(String)
    }

    private(set) var phase: Phase = .idle

    func load(_ request: SourceCropRequest, using fetch: SourceCropFetch) async {
        phase = .loading
        do {
            if let crop = try await fetch(request) {
                phase = .loaded(crop)
            } else {
                phase = .empty
            }
        } catch {
            if error.isCancellationError {
                // A newer request superseded this one — leave the phase for the
                // in-flight load to set; don't flash a spurious error.
                return
            }
            phase = .failed(error.localizedDescription)
        }
    }
}

// MARK: - View

/// The reusable "show me the source" component (#2105). Renders the cropped
/// source region (image or verbatim text) for any bbox/char-anchored record.
/// Cross-platform SwiftUI — no AppKit-only APIs — so it works on macOS,
/// iPadOS, and iOS. Reload is keyed on the request, so re-selecting a row
/// re-fetches without a manual refresh.
struct SourceSnippet: View {
    let request: SourceCropRequest
    let fetch: SourceCropFetch
    /// Caps the rendered evidence so a tall crop can't blow out the inspector
    /// column; the image scales to fit and stays scrollable-free.
    var maxImageHeight: CGFloat = 160

    @State private var loader = SourceSnippetLoader()

    var body: some View {
        content
            .frame(maxWidth: .infinity, alignment: .leading)
            .task(id: request) {
                await loader.load(request, using: fetch)
            }
    }

    @ViewBuilder
    private var content: some View {
        switch loader.phase {
        case .idle, .loading:
            ProgressView()
                .controlSize(.small)
                .frame(maxWidth: .infinity, minHeight: 44)
                .accessibilityLabel("Loading source region")

        case .loaded(.image(let image)):
            Image(platformImage: image)
                .resizable()
                .aspectRatio(contentMode: .fit)
                .frame(maxHeight: maxImageHeight)
                .clipShape(RoundedRectangle(cornerRadius: 6))
                .overlay(
                    RoundedRectangle(cornerRadius: 6)
                        .stroke(Color.secondary.opacity(0.25), lineWidth: 0.5)
                )
                .accessibilityLabel("Cropped source image")

        case .loaded(.text(let text)):
            Text(text)
                .font(.callout)
                .textSelection(.enabled)
                .padding(8)
                .frame(maxWidth: .infinity, alignment: .leading)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(Color.secondary.opacity(0.08))
                )
                .accessibilityLabel("Source text: \(text)")

        case .empty:
            placeholder("No source region", systemImage: "doc.text.magnifyingglass")

        case .failed(let message):
            placeholder(message, systemImage: "exclamationmark.triangle")
        }
    }

    @ViewBuilder
    private func placeholder(_ message: String, systemImage: String) -> some View {
        Label(message, systemImage: systemImage)
            .font(.caption)
            .foregroundStyle(.secondary)
            .frame(maxWidth: .infinity, minHeight: 44, alignment: .leading)
    }
}
