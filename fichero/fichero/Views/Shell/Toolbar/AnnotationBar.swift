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
    /// Labels beneath the glyphs — driven by the same switch as the workflow
    /// bar's labels (Daniel, 2026-08-30: "text underneath that is shown if I
    /// show it in the top toolbar").
    var showsLabels = false

    var body: some View {
        HStack(spacing: 10) {
            Spacer(minLength: 0)
            PreviewMarkupToolsRow(showsLabels: showsLabels)
            Spacer(minLength: 0)
        }
        // Real margins (Daniel, 2026-08-30: "left right margins should be
        // more") — the row breathes instead of hugging the pane edges.
        .padding(.horizontal, 28)
        .frame(height: showsLabels ? 52 : 38)
        .frame(maxWidth: .infinity)
        .background(.bar)
        .overlay(alignment: .bottom) { Divider() }
        .accessibilityIdentifier("annotationBar")
    }
}
