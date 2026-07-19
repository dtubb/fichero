import SwiftUI

// MARK: - ReaderToolbar

/// One unified, persistent reader toolbar shared by the image viewer and the PDF
/// viewer (#2423 / #2421). It sits at the **bottom** of the canvas and renders
/// every tool section for every document type, **disabling (greying)** the tools
/// that don't apply to the current document instead of hiding them — so the bar
/// is stable and the user always sees the full capability set.
///
/// Capability is expressed by which inputs the host passes:
///   • `pageNav == nil`           → page navigation greyed (e.g. a single image)
///   • `magnifierEnabled == nil`  → magnifier-panel toggle greyed (e.g. a PDF page)
///   • `loupe* == nil`            → loupe greyed
///   • `isEditing == nil`         → image-edit greyed (e.g. a PDF page)
///   • `onAnnotate == nil`        → annotation section greyed
///
/// Split-axis (h/v) buttons are injected automatically by `MiniToolbar` from the
/// `\.splitAxisActions` environment, so split keeps working for both viewers.
///
/// The control sections live in `ReaderToolbar+Controls.swift` and the overflow /
/// layout menus in `ReaderToolbar+Overflow.swift`; the shared value types are in
/// `ReaderToolbarTypes.swift`. This file owns the layout spine (`body`), the
/// cluster wiring, and the collapsible-cluster helper.
struct ReaderToolbar: View {
    // On compact width (iPhone) the desktop-centric zoom in/out + fit/actual-size
    // controls are dropped — pinch-zoom is the platform idiom there, so the
    // explicit scaling buttons are clutter (#2549). macOS reports `nil` and
    // iPad-regular reports `.regular`, so both keep the full control set; only
    // `.compact` (iPhone) hides zoom/fit. Page navigation is kept on every size
    // class — a reader still needs to turn pages.
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    // `internal` (not `private`) so `closePane` in ReaderToolbar+Controls.swift
    // can read it — a `private` member is invisible to an extension in another file.
    @Environment(\.splitAxisActions) var splitAxisActions
    @AppStorage("readerToolbar.pageNavExpanded") private var pageNavExpanded = false
    @AppStorage("readerToolbar.zoomExpanded") private var zoomExpanded = false
    @AppStorage("readerToolbar.toolsExpanded") private var toolsExpanded = false

    private var isCompact: Bool { horizontalSizeClass == .compact }

    // ─── Pane chrome (the PDF reader supplies these; the image viewer leaves nil) ───
    var title: String?
    var onClose: (() -> Void)?
    /// True when the pane is inside an active split — the × collapses the split.
    var isInSplit: Bool = false

    // ─── Page navigation (nil ⇒ greyed) ───
    var pageNav: ReaderPageNav?

    // ─── Page layout (#2090; nil ⇒ picker hidden — nothing to arrange) ───
    var pageLayout: Binding<PageLayoutMode>?

    // ─── Zoom (always available for both image + PDF) ───
    var scalePercent: Int
    var zoomIn: () -> Void
    var zoomOut: () -> Void
    var fitToWindow: () -> Void
    var actualSize: () -> Void

    // ─── Magnifier panel (image only; nil ⇒ greyed) ───
    var magnifierEnabled: Binding<Bool>?

    // ─── Loupe (image + PDF; nil ⇒ greyed) ───
    var loupeEnabled: Binding<Bool>?
    var loupeLocked: Binding<Bool>?
    var loupeMagnification: Binding<Double>?

    // ─── Image editing (image only; nil ⇒ greyed) ───
    /// Drives the host's view↔edit toggle. Lives here — at the bottom, on the same
    /// baseline as the zoom/loupe icons — instead of floating over the split
    /// control, which is the #2421 overlap this bar removes.
    var isEditing: Binding<Bool>?

    // ─── Annotation (image + PDF; nil ⇒ greyed) ───
    var onAnnotate: ((ReaderAnnotationTool) -> Void)?

    // ─── Pin (PDF only; nil ⇒ hidden, it is pane chrome not a tool) ───
    var isPinned: Binding<Bool>?
    var onTogglePin: (() -> Void)?

    // Primary controls (chrome / page-nav / zoom / fit) stay inline; the
    // secondary tools (magnifier / loupe / edit / annotation) collapse into a
    // trailing '…' menu when the pane is too narrow to show them — e.g. two PDF
    // panes side by side (#2488). `ViewThatFits` picks the inline row when it
    // fits and falls back to the overflow menu otherwise, so the bar never
    // wraps or crams. Mirrors the content-rail overflow pattern (#1733).
    var body: some View {
        MiniToolbar(content: {
            chromeSection
            pageNavCluster
            pageLayoutSection
            Spacer(minLength: 0)
            adaptiveToolsRow
            Spacer()
        }, trailing: {
            pinButton
        })
    }

    // `internal` (not `private`) so the control sections in
    // ReaderToolbar+Controls.swift and the menus in ReaderToolbar+Overflow.swift
    // can reuse it — a `private` member is invisible to an extension in another file.
    var sectionDivider: some View {
        Divider().frame(height: 16)
    }

    // MARK: - Clusters

    @ViewBuilder
    private var pageNavCluster: some View {
        if pageNav != nil {
            ReaderToolbarCluster(
                isExpanded: $pageNavExpanded,
                collapsedIcon: "chevron.left.chevron.right",
                collapsedHelp: "Show page controls"
            ) {
                pageNavSection
            }
        }
    }

    @ViewBuilder
    private var zoomCluster: some View {
        ReaderToolbarCluster(
            isExpanded: $zoomExpanded,
            collapsedIcon: "magnifyingglass",
            collapsedHelp: "Show zoom controls"
        ) {
            zoomSection
            fitSection
        }
    }

    @ViewBuilder
    private var secondaryToolsCluster: some View {
        ReaderToolbarCluster(
            isExpanded: $toolsExpanded,
            collapsedIcon: "ellipsis.circle",
            collapsedHelp: "Show reader tools"
        ) {
            inlineSecondaryTools
        }
    }

    /// The shared adaptive row keeps the reader on the same mini-toolbar
    /// budget/overflow policy as the library and sidebar surfaces (#3201).
    private var adaptiveToolsRow: some View {
        AdaptiveMiniToolbarRow {
            // Zoom/fit are desktop-centric; on compact width pinch-zoom handles
            // scaling, so we drop them to de-clutter the bar (#2549).
            if !isCompact {
                zoomCluster
            }
        } secondary: {
            secondaryToolsCluster
        } overflowMenu: {
            overflowMenu
        }
    }
}

private struct ReaderToolbarCluster<Expanded: View>: View {
    @Binding var isExpanded: Bool
    let collapsedIcon: String
    let collapsedHelp: String
    let expandedContent: Expanded

    init(
        isExpanded: Binding<Bool>,
        collapsedIcon: String,
        collapsedHelp: String,
        @ViewBuilder expandedContent: () -> Expanded
    ) {
        self._isExpanded = isExpanded
        self.collapsedIcon = collapsedIcon
        self.collapsedHelp = collapsedHelp
        self.expandedContent = expandedContent()
    }

    var body: some View {
        ViewThatFits(in: .horizontal) {
            if isExpanded {
                HStack(spacing: 4) {
                    Button {
                        withAnimation(.easeInOut(duration: 0.15)) {
                            isExpanded.toggle()
                        }
                    } label: {
                        Image(systemName: collapsedIcon)
                            .frame(
                                minWidth: MiniToolbar<EmptyView, EmptyView>.touchTargetSide,
                                minHeight: MiniToolbar<EmptyView, EmptyView>.touchTargetSide
                            )
                    }
                    .buttonStyle(.plain)
                    .foregroundStyle(.secondary)
                    .help("Collapse")
                    .accessibilityLabel("Collapse")

                    expandedContent
                }
            }
            Button {
                withAnimation(.easeInOut(duration: 0.15)) {
                    isExpanded.toggle()
                }
            } label: {
                Image(systemName: collapsedIcon)
                    .frame(
                        minWidth: MiniToolbar<EmptyView, EmptyView>.touchTargetSide,
                        minHeight: MiniToolbar<EmptyView, EmptyView>.touchTargetSide
                    )
            }
            .buttonStyle(.plain)
            .foregroundStyle(.secondary)
            .help(collapsedHelp)
            .accessibilityLabel(collapsedHelp)
        }
    }
}
