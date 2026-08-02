import SwiftUI

// MARK: - Overflow ('…') collapse (#2488)

extension ReaderToolbar {
    /// A pull-down for the reading layout (#2090). Offers the PDFKit-native
    /// (Tier 1) modes — single / single-continuous / two-up / two-up-continuous;
    /// the 3-up / 4-up grid modes join once the custom N-up renderer lands
    /// (Tier 2). Hidden when the host passes no `pageLayout` binding.
    @ViewBuilder
    var pageLayoutSection: some View {
        if let pageLayout {
            Menu {
                ForEach(PageLayoutMode.allCases.filter(\.isPDFKitNative)) { mode in
                    Button {
                        pageLayout.wrappedValue = mode
                    } label: {
                        Label(
                            mode.label,
                            systemImage: pageLayout.wrappedValue == mode ? "checkmark" : mode.systemImage
                        )
                    }
                }
            } label: {
                Image(systemName: pageLayout.wrappedValue.systemImage)
                    .foregroundStyle(.secondary)
            }
            .menuIndicator(.hidden)
            .fixedSize()
            .help("Page layout — single page, continuous scroll, or two-up spread")
            .accessibilityLabel("Page layout")
            .accessibilityIdentifier("readerPageLayout")

            sectionDivider
        }
    }

    /// The secondary tools rendered inline, in priority order. This is the
    /// preferred `ViewThatFits` candidate; when it doesn't fit, the overflow
    /// menu is used instead.
    var inlineSecondaryTools: some View {
        HStack(spacing: 12) {
            magnifierButton
            textBoxesButton
            loupeSection
            editButton
            annotationSection
        }
        .fixedSize(horizontal: true, vertical: false)
    }

    /// Toggle for the OCR text-box overlay (#4309). Greyed when the host
    /// passes no binding (e.g. a surface without page geometry).
    @ViewBuilder
    var textBoxesButton: some View {
        let binding = textBoxesEnabled ?? .constant(false)
        Button {
            binding.wrappedValue.toggle()
        } label: {
            Image(systemName: "text.viewfinder")
                .readerIconTarget()
        }
        .accessibilityLabel("Text Boxes")
        .buttonStyle(.plain)
        .foregroundColor(binding.wrappedValue ? .accentColor : .primary)
        .disabled(textBoxesEnabled == nil)
        .help(
            textBoxesEnabled == nil
                ? "Text boxes (not available for this document)"
                : "Show recognized text boxes"
        )
    }

    /// Trailing '…' menu holding the secondary tools when the bar is too narrow
    /// to show them inline. Greyed (disabled) tools stay listed but inert, so
    /// the menu's contents match the inline row exactly.
    var overflowMenu: some View {
        Menu {
            Toggle("Magnifier Panel", isOn: magnifierEnabled ?? .constant(false))
                .disabled(magnifierEnabled == nil)

            Toggle("Text Boxes", isOn: textBoxesEnabled ?? .constant(false))
                .disabled(textBoxesEnabled == nil)

            Toggle("Loupe", isOn: loupeEnabled ?? .constant(false))
                .disabled(loupeEnabled == nil)
            if loupeEnabled?.wrappedValue == true, loupeLocked != nil {
                Toggle("Lock Loupe", isOn: loupeLocked ?? .constant(false))
            }

            Divider()

            Toggle("Edit Image", isOn: isEditing ?? .constant(false))
                .disabled(isEditing == nil)

            Divider()

            Section("Annotate") {
                ForEach(ReaderAnnotationTool.allCases) { tool in
                    Button {
                        onAnnotate?(tool)
                    } label: {
                        Label(tool.label, systemImage: tool.icon)
                    }
                    .disabled(onAnnotate == nil)
                }
            }
        } label: {
            Image(systemName: "ellipsis.circle")
        }
        .menuIndicator(.hidden)
        .fixedSize()
        .help("More tools")
        .accessibilityLabel("More tools")
        .accessibilityIdentifier("readerToolbarOverflow")
    }
}
