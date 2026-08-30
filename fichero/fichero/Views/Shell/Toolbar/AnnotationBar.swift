import SwiftUI

/// The WINDOW-level annotation bar (Daniel, 2026-08-30, Preview.app as the
/// model): below the toolbar, above the workflow bar, toggled by the
/// toolbar's pencil. Annotation is not a preview-pane feature — the same
/// verbs (select, marquee, line, highlight, note, star) should reach an
/// image, a PDF, the reader, an entity, an artifact, a row in library or
/// data-entry view. The bar is the one home for those verbs; surfaces
/// consume its notifications (`.previewAnnotateTool` / `.previewRegionVerb`)
/// as they learn to. Today the preview canvases answer; the rest join
/// without the bar moving.
struct AnnotationBar: View {
    var body: some View {
        HStack(spacing: 6) {
            Spacer(minLength: 0)
            PreviewMarkupToolsRow()
            starButton
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 10)
        .frame(height: 38)
        .frame(maxWidth: .infinity)
        .background(.bar)
        .overlay(alignment: .bottom) { Divider() }
        .accessibilityIdentifier("annotationBar")
    }

    /// "Star anything" — the bookmark annotation kind, whole-item, no region.
    private var starButton: some View {
        Button {
            NotificationCenter.default.post(
                name: .previewAnnotateTool, object: PreviewMarkupTool.star.rawValue
            )
        } label: {
            Label(PreviewMarkupTool.star.label, systemImage: PreviewMarkupTool.star.icon)
                .labelStyle(.iconOnly)
        }
        .buttonStyle(.borderless)
        .help("Star this item")
        .accessibilityLabel("Star")
        .accessibilityIdentifier("annotationBarStar")
    }
}
