// swiftlint:disable file_length
import SwiftUI

// MARK: - Reader annotation tools

/// The annotation tools surfaced by the unified reader toolbar.
///
/// The toolbar only *emits* the requested tool to its host via `onAnnotate`.
/// Region-anchored creation (drawing a highlight box / dropping a pin) and
/// on-canvas rendering of saved annotations are owned by **#2458**; until that
/// lands, hosts wire these to a clearly-marked stub. The page-scoped note path
/// (`AnnotationStore.addNote`) already exists in the backend.
enum ReaderAnnotationTool: String, CaseIterable, Identifiable {
    case highlight
    case note
    case bookmark

    var id: String { rawValue }

    /// SF Symbol — mirrors `AnnotationKind.icon` so the reader and inspector agree.
    var icon: String {
        switch self {
        case .highlight: return "highlighter"
        case .note: return "note.text"
        case .bookmark: return "bookmark"
        }
    }

    var label: String {
        switch self {
        case .highlight: return "Highlight"
        case .note: return "Add Note"
        case .bookmark: return "Bookmark"
        }
    }
}

// MARK: - Page navigation descriptor

/// Page-within-document navigation state for the reader toolbar. Supplied by the
/// PDF reader; `nil` (or a single-page document) greys the nav controls out.
struct ReaderPageNav {
    let pageIndex: Int
    let pageCount: Int
    let canGoPrevious: Bool
    let canGoNext: Bool
    let goPrevious: () -> Void
    let goNext: () -> Void
}

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
struct ReaderToolbar: View {
    // On compact width (iPhone) the desktop-centric zoom in/out + fit/actual-size
    // controls are dropped — pinch-zoom is the platform idiom there, so the
    // explicit scaling buttons are clutter (#2549). macOS reports `nil` and
    // iPad-regular reports `.regular`, so both keep the full control set; only
    // `.compact` (iPhone) hides zoom/fit. Page navigation is kept on every size
    // class — a reader still needs to turn pages.
    @Environment(\.horizontalSizeClass) private var horizontalSizeClass
    @Environment(\.splitAxisActions) private var splitAxisActions
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
            Spacer(minLength: 0)
            // Zoom/fit are desktop-centric; on compact width pinch-zoom handles
            // scaling, so we drop them to de-clutter the bar (#2549).
            if !isCompact {
                zoomCluster
            }
            secondaryToolsCluster
            Spacer()
        }, trailing: {
            pinButton
        })
    }

    private var sectionDivider: some View {
        Divider().frame(height: 16)
    }

    // MARK: - Chrome (close + title)

    private func closePane() {
        if let actions = splitAxisActions, actions.hasVertical || actions.hasHorizontal {
            actions.onCollapseSplit()
            return
        }
        onClose?()
    }

    @ViewBuilder
    private var chromeSection: some View {
        if onClose != nil || isInSplit {
            Button {
                closePane()
            } label: {
                Image(systemName: "xmark.circle.fill")
                    .foregroundStyle(.secondary)
            }
            .buttonStyle(.plain)
            .help(isInSplit ? "Close this split" : "Close this pane")
            .accessibilityLabel(isInSplit ? "Close this split" : "Close this pane")

            sectionDivider
        }

        if let title, !title.isEmpty {
            Image(systemName: "doc.richtext")
                .imageScale(.small)
                .foregroundStyle(.secondary)
            Text(title)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)

            sectionDivider
        }
    }

    // MARK: - Page navigation

    @ViewBuilder
    private var pageNavSection: some View {
        let enabled = (pageNav?.pageCount ?? 0) > 1
        let indexLabel = pageNav.map { "\($0.pageIndex + 1) / \($0.pageCount)" } ?? "– / –"

        Button {
            pageNav?.goPrevious()
        } label: {
            Image(systemName: "chevron.left")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .disabled(!(enabled && (pageNav?.canGoPrevious ?? false)))
        .help("Previous Page")
        .accessibilityLabel("Previous Page")
        .accessibilityIdentifier("pdfPreviousPage")

        Text(indexLabel)
            .font(.caption)
            .monospacedDigit()
            .foregroundStyle(.secondary)
            .frame(minWidth: 48)

        Button {
            pageNav?.goNext()
        } label: {
            Image(systemName: "chevron.right")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .disabled(!(enabled && (pageNav?.canGoNext ?? false)))
        .help("Next Page")
        .accessibilityLabel("Next Page")
        .accessibilityIdentifier("pdfNextPage")

        sectionDivider
    }

    // MARK: - Zoom

    @ViewBuilder
    private var zoomSection: some View {
        Button(action: zoomOut) {
            Image(systemName: "minus.magnifyingglass")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .help("Zoom Out")
        .accessibilityLabel("Zoom Out")

        Text("\(scalePercent)%")
            .font(.caption)
            .monospacedDigit()
            .frame(width: 50)

        Button(action: zoomIn) {
            Image(systemName: "plus.magnifyingglass")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .help("Zoom In")
        .accessibilityLabel("Zoom In")

        sectionDivider
    }

    @ViewBuilder
    private var fitSection: some View {
        Button(action: fitToWindow) {
            Image(systemName: "arrow.up.left.and.arrow.down.right")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .help("Fit to Window")
        .accessibilityLabel("Fit to Window")

        Button(action: actualSize) {
            Image(systemName: "1.square")
                .foregroundStyle(.secondary)
        }
        .buttonStyle(.plain)
        .help("Actual Size (100%)")
        .accessibilityLabel("Actual Size (100%)")

        sectionDivider
    }

    // MARK: - Magnifier panel

    @ViewBuilder
    private var magnifierButton: some View {
        let binding = magnifierEnabled ?? .constant(false)
        Button {
            binding.wrappedValue.toggle()
        } label: {
            Image(systemName: "rectangle.bottomhalf.inset.filled")
        }
        .buttonStyle(.plain)
        .foregroundColor(binding.wrappedValue ? .accentColor : .primary)
        .disabled(magnifierEnabled == nil)
        .help(magnifierEnabled == nil ? "Magnifier panel (not available for this document)" : "Magnifier Panel")
        .accessibilityLabel("Magnifier Panel")
    }

    // MARK: - Loupe

    @ViewBuilder
    private var loupeSection: some View {
        let enabledBinding = loupeEnabled ?? .constant(false)
        let lockedBinding = loupeLocked ?? .constant(false)

        HStack(spacing: 4) {
            Button {
                enabledBinding.wrappedValue.toggle()
            } label: {
                Image(systemName: enabledBinding.wrappedValue
                        ? "magnifyingglass.circle.fill"
                        : "magnifyingglass.circle")
            }
            .buttonStyle(.plain)
            .foregroundColor(enabledBinding.wrappedValue ? .accentColor : .primary)
            .disabled(loupeEnabled == nil)
            .help(loupeEnabled == nil ? "Loupe (not available for this document)" : "Toggle loupe")
            .accessibilityLabel("Loupe")

            if loupeEnabled != nil, enabledBinding.wrappedValue {
                Button {
                    lockedBinding.wrappedValue.toggle()
                } label: {
                    Image(systemName: lockedBinding.wrappedValue ? "lock.fill" : "lock.open")
                }
                .buttonStyle(.plain)
                .foregroundColor(lockedBinding.wrappedValue ? .accentColor : .secondary)
                .help(lockedBinding.wrappedValue ? "Unlock loupe" : "Lock loupe")
                .accessibilityLabel(lockedBinding.wrappedValue ? "Unlock loupe" : "Lock loupe")

                if let mag = loupeMagnification {
                    Text(String(format: "%.1fx", mag.wrappedValue))
                        .font(.caption2)
                        .monospacedDigit()
                        .foregroundColor(.secondary)
                        .frame(width: 32)

                    Slider(value: mag, in: 1...8, step: 0.5)
                        .frame(width: 80)
                }
            }
        }

        sectionDivider
    }

    // MARK: - Image editing

    @ViewBuilder
    private var editButton: some View {
        let binding = isEditing ?? .constant(false)
        Button {
            withAnimation(.easeInOut(duration: 0.15)) {
                binding.wrappedValue.toggle()
            }
        } label: {
            Image(systemName: binding.wrappedValue ? "pencil.circle.fill" : "pencil.circle")
        }
        .buttonStyle(.plain)
        .foregroundColor(binding.wrappedValue ? .accentColor : .primary)
        .disabled(isEditing == nil)
                .help(isEditing == nil
                ? "Image editing (not available for this document)"
                : (binding.wrappedValue
                    ? "Done — return to viewing"
                    : "Edit image (crop, rotate, straighten, enhance, remove background)"))
        .accessibilityLabel(binding.wrappedValue ? "Done editing" : "Edit image")
        .accessibilityIdentifier("canvasEditModeToggle")

        sectionDivider
    }

    // MARK: - Annotation

    @ViewBuilder
    private var annotationSection: some View {
        ForEach(ReaderAnnotationTool.allCases) { tool in
            Button {
                onAnnotate?(tool)
            } label: {
                Image(systemName: tool.icon)
            }
            .buttonStyle(.plain)
            .disabled(onAnnotate == nil)
            .help(onAnnotate == nil ? "\(tool.label) (not available for this document)" : tool.label)
            .accessibilityLabel(tool.label)
            .accessibilityIdentifier("readerAnnotate_\(tool.rawValue)")
        }
    }

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

    // MARK: - Pin (trailing, after split buttons)

    @ViewBuilder
    private var pinButton: some View {
        if let isPinned, let onTogglePin {
            sectionDivider

            Button(action: onTogglePin) {
                Image(systemName: isPinned.wrappedValue ? "pin.fill" : "pin")
                    .font(.system(size: 11))
            }
            .buttonStyle(.plain)
            .foregroundStyle(isPinned.wrappedValue ? Color.accentColor : Color.secondary)
            .help(isPinned.wrappedValue ? "Unpin — follow current selection" : "Pin to this document")
            .accessibilityLabel(isPinned.wrappedValue ? "Unpin" : "Pin to this document")
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

// MARK: - Overflow ('…') collapse (#2488)

extension ReaderToolbar {
    /// The secondary tools rendered inline, in priority order. This is the
    /// preferred `ViewThatFits` candidate; when it doesn't fit, the overflow
    /// menu is used instead.
    var inlineSecondaryTools: some View {
        HStack(spacing: 12) {
            magnifierButton
            loupeSection
            editButton
            annotationSection
        }
        .fixedSize(horizontal: true, vertical: false)
    }

    /// Trailing '…' menu holding the secondary tools when the bar is too narrow
    /// to show them inline. Greyed (disabled) tools stay listed but inert, so
    /// the menu's contents match the inline row exactly.
    var overflowMenu: some View {
        Menu {
            Toggle("Magnifier Panel", isOn: magnifierEnabled ?? .constant(false))
                .disabled(magnifierEnabled == nil)

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
