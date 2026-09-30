import SwiftUI

// MARK: - Preview head controls (Daniel, 2026-08-29, Preview.app as the model)
//
// The pane head gains the controls the bottom bar loses:
//   • pages ‹ › (and an up-to-parent step) LEFT of the breadcrumb — inside
//     the identity capsule, after the kind/lens selector;
//   • region show/hide + a renditions MENU top-right by the breadcrumb — the
//     reader's transcript/translation menu grammar;
//   • a pencil toggle that slides the markup row out UNDER the head.

/// The identity-capsule content: the Preview ∨ / Edit selector, then the
/// paging cluster (up-to-parent · ‹ ›) left of the breadcrumb.
struct PreviewHeadSelectorGroup: View {
    let selector: PaneKindSelector<PreviewLens>
    let chrome: PreviewPaneChrome
    /// Non-nil when the shown document HAS a visual parent (Daniel,
    /// 2026-08-29: a region/page-part needs an obvious one-click way BACK UP
    /// to the spread). Invoking it shows the parent in this pane.
    var onUpToParent: (() -> Void)?

    var body: some View {
        selector

        Divider().frame(height: PaneHeadMetrics.dividerHeight)

        if let onUpToParent {
            // Not a bare chevron.up (Daniel, 2026-09-02): sitting beside the
            // page arrows it read as "rendition up" — an axis it isn't. The
            // turn-up glyph says "go up a level", which is what it does.
            Button(action: onUpToParent) {
                Image(systemName: "arrow.turn.left.up")
                    .font(.callout)
            }
            .buttonStyle(.borderless)
            // No key binding for the three nav controls here: ⌘[ / ⌘] belong
            // to `CanvasMenuCommands` and ⌘⌥[ / ⌘⌥] to the magnifier's zoom
            // in `ImagePreviewMenuCommands`. A second view binding the same
            // chord doesn't win, it just makes one of the two stop working.
            .help("Up to the parent image — show the spread this part came from")
            .accessibilityLabel("Up to the parent image")
            .accessibilityIdentifier("previewHeadUpToParent")
        }

        pageArrows
    }

    /// ‹ › page/sibling stepping. Uses the canvas-published nav when there is
    /// one (PDF pages; image sibling walk with position), else falls back to
    /// the sibling-swipe seam so the arrows always work — the reliable
    /// alternative to the swipe the scroll view eats (ruling 6).
    @ViewBuilder
    private var pageArrows: some View {
        let nav = chrome.pageNav
        Button {
            if let nav { nav.goPrevious() } else {
                NotificationCenter.default.post(name: .previewSiblingSwipe, object: -1)
            }
        } label: {
            Image(systemName: "chevron.left").font(.callout)
        }
        .buttonStyle(.borderless)
        .disabled(nav.map { !$0.canGoPrevious } ?? false)
        .help("Previous page in this document")
        .accessibilityLabel("Previous page")
        .accessibilityIdentifier("previewHeadPreviousPage")

        if let nav {
            Text("\(nav.pageIndex + 1)/\(nav.pageCount)")
                .font(.caption)
                .monospacedDigit()
                .foregroundStyle(.secondary)
        }

        Button {
            if let nav { nav.goNext() } else {
                NotificationCenter.default.post(name: .previewSiblingSwipe, object: 1)
            }
        } label: {
            Image(systemName: "chevron.right").font(.callout)
        }
        .buttonStyle(.borderless)
        .disabled(nav.map { !$0.canGoNext } ?? false)
        .help("Next page in this document")
        .accessibilityLabel("Next page")
        .accessibilityIdentifier("previewHeadNextPage")
    }
}

/// The head's top-right lenses: the zoom-cluster toggle, and the renditions
/// menu.
struct PreviewHeadLensControls: View {
    let chrome: PreviewPaneChrome
    /// The window's Edit Segments mode -- the SAME state the What-to-show toggle writes, so
    /// the two switches can never disagree (`WindowState.isEditingSegments`).
    @Environment(WindowState.self) private var windowState: WindowState?

    /// Whether the floating magnification cluster (mini-map / zoom pill /
    /// loupe + magnifier toggles) is showing over the canvas.
    @PaneStorage("imagePreview.zoomControlsVisible") private var zoomControlsVisible = true

    var body: some View {
        editSegmentsToggle
        zoomControlsToggle
        renditionSteppers
        renditionsMenu
    }

    /// Edit Segments in the HEAD (ruled 2026-09-27, Q3): the mode was reachable only inside the
    /// What-to-show menu, which is a place to look for display options, not for "can I change
    /// this page". Both switches write one state; the menu entry stays.
    @ViewBuilder
    private var editSegmentsToggle: some View {
        if chrome.canEditSegments, let windowState {
            let isEditing = windowState.isEditingSegments
            Button {
                windowState.isEditingSegments.toggle()
            } label: {
                Image(systemName: "rectangle.and.pencil.and.ellipsis")
            }
            .buttonStyle(.borderless)
            .foregroundStyle(isEditing ? Color.accentColor : Color.secondary)
            .help(isEditing ? "Stop editing segments -- the page is for reading"
                     : "Edit Segments -- draw, move, join and delete segments on this page")
            .accessibilityLabel("Edit Segments")
            .accessibilityValue(isEditing ? "On" : "Off")
            .accessibilityIdentifier("previewHeadEditSegments")
        }
    }

    /// ▲▼ rendition stepping RIGHT of the breadcrumb (Daniel, 2026-09-02:
    /// "left right to left of breadcrumb, renditions to right of breadcrumbs").
    /// The vertical swipe flips the same axis; these buttons make it VISIBLE —
    /// a page with one rendition shows nothing, which is why the axis felt
    /// dead on documents that had nothing to flip to.
    @ViewBuilder
    private var renditionSteppers: some View {
        if chrome.renditionNames.count > 1 {
            Button {
                chrome.selectRendition?(chrome.renditionIndex - 1)
            } label: {
                Image(systemName: "chevron.up").font(.callout)
            }
            .buttonStyle(.borderless)
            .disabled(chrome.renditionIndex <= 0)
            .help("Previous rendition of this page (swipe up)")
            .accessibilityLabel("Previous rendition")
            .accessibilityIdentifier("previewHeadRenditionPrevious")

            Button {
                chrome.selectRendition?(chrome.renditionIndex + 1)
            } label: {
                Image(systemName: "chevron.down").font(.callout)
            }
            .buttonStyle(.borderless)
            .disabled(chrome.renditionIndex >= chrome.renditionNames.count - 1)
            .help("Next rendition of this page (swipe down)")
            .accessibilityLabel("Next rendition")
            .accessibilityIdentifier("previewHeadRenditionNext")
        }
    }

    /// The word-boundaries toggle that used to sit here is GONE (Daniel,
    /// 2026-08-31: "not needed as bottom metadata has that"). It was also the
    /// desync: it wrote `imagePreview.ocrBoxesEnabled` AND
    /// `pdfPreview.ocrBoxesEnabled` while labelling itself "regions", so the
    /// head and the bottom menu disagreed about which switch was which. One
    /// owner now — the quiet bar's what-to-show menu — and this seat goes to
    /// the control the head actually lacked.
    private var zoomControlsToggle: some View {
        Button {
            zoomControlsVisible.toggle()
        } label: {
            // ONE icon, both states (Daniel, 2026-09-01). Swapping the glyph
            // for +/− made the button read as "zoom in" / "zoom out" rather
            // than "show the zoom controls" — a toggle whose picture changes
            // is a different button. The loupe-with-a-plus stays put; only the
            // tint says whether the cluster is on.
            Image(systemName: "plus.magnifyingglass")
        }
        .buttonStyle(.borderless)
        .foregroundStyle(zoomControlsVisible ? Color.accentColor : Color.secondary)
        // Not ⌘⌥Z: any "z" key equivalent outside the Edit menu trips the
        // ⌘Z single-owner guard (#4354).
        .help("Show or Hide Zoom Controls (⌘⌥E)")
        .keyboardShortcut("e", modifiers: [.command, .option])
        .accessibilityLabel("Show or hide zoom controls")
        .accessibilityIdentifier("previewHeadZoomControlsToggle")
    }

    /// Renditions as a MENU, the reader's transcript/translation grammar
    /// (Daniel, 2026-08-29) — hidden when the page has at most one rendition.
    @ViewBuilder
    private var renditionsMenu: some View {
        if chrome.renditionNames.count > 1 {
            Menu {
                ForEach(Array(chrome.renditionNames.enumerated()), id: \.offset) { index, name in
                    Button {
                        chrome.selectRendition?(index)
                    } label: {
                        if index == chrome.renditionIndex {
                            Label(name, systemImage: "checkmark")
                        } else {
                            Text(name)
                        }
                    }
                }
            } label: {
                Text(currentRenditionName)
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            .menuStyle(.borderlessButton)
            .fixedSize()
            .help("Which rendition of this page is showing — original, enhanced, deskewed…")
            .accessibilityLabel("Renditions")
            .accessibilityIdentifier("previewHeadRenditionsMenu")
        }
    }

    private var currentRenditionName: String {
        let names = chrome.renditionNames
        guard names.indices.contains(chrome.renditionIndex) else { return "Rendition" }
        return names[chrome.renditionIndex]
    }
}
