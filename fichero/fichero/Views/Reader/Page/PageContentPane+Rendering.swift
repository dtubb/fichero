import SwiftUI

// MARK: - Rendering

extension PageContentPane {

    @ViewBuilder
    func pageContentScroll(_ content: String) -> some View {
        if let sourceHighlight {
            // Claim-source focus keeps the SwiftUI scroll-to path so the matched
            // span centres in view (#1189). Annotation highlights resume once
            // the transient claim focus clears.
            ScrollViewReader { proxy in
                ScrollView {
                    highlightedPageContent(sourceHighlight)
                }
                .onChange(of: sourceHighlightToken) { _, _ in
                    withAnimation(.easeInOut(duration: 0.2)) {
                        proxy.scrollTo(Self.claimSourceHighlightId, anchor: .center)
                    }
                }
            }
        } else {
            // Normal reading: AppKit-backed selectable text that draws saved
            // highlights and reports the selection for the annotation toolbar.
            AnnotatableTextView(
                text: content,
                highlights: highlightRanges(for: content),
                selection: $selectionRange
            )
        }
    }

    func highlightedPageContent(_ highlight: PageContentClaimSourceHighlight) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            if !highlight.before.isEmpty {
                Text(highlight.before)
            }
            Text(highlight.highlighted)
                .padding(.horizontal, 2)
                .background(Color.yellow.opacity(0.35))
                .clipShape(RoundedRectangle(cornerRadius: 3))
                .id(Self.claimSourceHighlightId)
            if !highlight.after.isEmpty {
                Text(highlight.after)
            }
        }
        .font(.system(.body, design: .serif))
        .lineSpacing(4)
        .frame(maxWidth: .infinity, alignment: .leading)
        .textSelection(.enabled)
        .padding(12)
    }

    @ViewBuilder
    func emptyState(title: String, subtitle: String) -> some View {
        VStack(spacing: 8) {
            Spacer()
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
            Text(subtitle)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
            Spacer()
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding(12)
    }
}
