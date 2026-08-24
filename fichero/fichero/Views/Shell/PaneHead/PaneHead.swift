import SwiftUI

// MARK: - The pane head (R1/R3/R5/R7, 2026-08-23)

/// Every pane's head: what it is, where you are, and what you can do to it.
///
/// R1 puts this at the TOP of every pane (the Xcode model) and retires the
/// per-pane bottom bars. R7 says it floats: Tahoe/golden-gate capsules OVER the
/// content, like the 3D canvas's control pill — no opaque grey bar, content
/// scrolls under.
///
/// **Grammar, left → right:**
/// ```
/// [✕ · kind ▾ lens ▾]        [ breadcrumb ]        [view controls · ⋯]
///  identity capsule            where you are         what you can do
/// ```
/// Close sits with the selector because both are about the pane's IDENTITY —
/// what it is and whether it exists — while the right capsule is about its
/// CONTENT. The breadcrumb takes the flexible middle and truncates from the
/// LEADING edge, because a deep path's tail ("… › Inbox › 1933") is the part
/// that identifies it; the head of the path is the part you can infer.
///
/// **R5: tools do not crowd the head.** Anything beyond the view controls
/// arrives as a second floating row, disclosed by the `⋯` toggle — the
/// Preview.app model. The head grows DOWNWARD, so nothing reflows sideways when
/// it opens.
///
/// One segment of a pane's breadcrumb title — a node with a face (Daniel,
/// 2026-08-23: "crumbs need icons that match sidebar and library").
struct PaneCrumb: Identifiable, Equatable {
    let id: String
    let name: String
    let icon: String
    /// `false` renders as plain text (e.g. a root the pane cannot navigate to).
    var isNavigable: Bool = true
    /// Icon colour, matching the sidebar/library rows (Daniel, 2026-08-23:
    /// "a folder is colorized like in sidebar / library view").
    var tint: Color = .secondary
}

struct PaneHead<Selector: View, Controls: View, Tools: View>: View {
    /// The path to what this pane is showing — "Marshall Diaries v4 › Inbox ›
    /// 1933", NEVER the pane's type name (R1: the title line IS the
    /// breadcrumb).
    let crumbs: [PaneCrumb]
    var onClose: (() -> Void)?
    /// Pin state, when this pane supports pinning to its current view. The
    /// pin menu renders automatically whenever a binding is supplied.
    var isPinned: Binding<Bool>?
    /// Crumb click navigates WITHIN this pane (ruling 2026-08-23). `nil`
    /// renders the crumbs as plain text.
    var onCrumb: ((PaneCrumb) -> Void)?
    /// The Xcode jump-bar grammar (Daniel, 2026-08-23): every segment —
    /// including the CURRENT one — is a menu of that node's children, so you
    /// can dive down as well as climb up. Sync so the menu can render; feed
    /// it from a cache.
    var crumbChildren: ((PaneCrumb) -> [PaneCrumb])?
    /// The two-level kind ▾ / lens ▾ control.
    @ViewBuilder var selector: () -> Selector
    /// The few controls that always apply to this pane kind.
    @ViewBuilder var controls: () -> Controls
    /// The disclosed second row. An empty `Tools` hides the `⋯` toggle, so a
    /// pane with nothing extra shows no affordance for it.
    @ViewBuilder var tools: () -> Tools

    @State private var showsTools = false
    /// Split actions arrive from the pane's own environment, so EVERY
    /// splittable pane gets the "+" menu automatically (Daniel, 2026-08-23:
    /// "close on left for all automatically, split and pin on the right
    /// automatically") — adopters wire nothing.
    @Environment(\.splitAxisActions) private var splitAxisActions

    var body: some View {
        VStack(alignment: .leading, spacing: PaneHeadMetrics.rowSpacing) {
            HStack(spacing: PaneHeadMetrics.capsuleSpacing) {
                identityCapsule
                breadcrumbCapsule
                Spacer(minLength: PaneHeadMetrics.capsuleSpacing)
                controlsCapsule
            }
            if showsTools {
                capsule { tools() }
            }
        }
        .padding(.vertical, PaneHeadMetrics.inset)
        .padding(.leading, PaneHeadMetrics.inset)
        // Extra trailing room (Daniel, 2026-08-23): the "+" must not sit
        // over a scroll bar when the pane has one.
        .padding(.trailing, PaneHeadMetrics.trailingInset)
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    /// True while this pane sits inside an active split — X then collapses
    /// THAT split (one at a time), never the whole pane kind (Daniel,
    /// 2026-08-23: "left X should close that split, not all of that type").
    private var isInSplit: Bool {
        splitAxisActions.map { $0.hasVertical || $0.hasHorizontal } ?? false
    }

    private var identityCapsule: some View {
        capsule {
            HStack(spacing: 6) {
                if onClose != nil || isInSplit {
                    Button {
                        if let actions = splitAxisActions, isInSplit {
                            actions.onCollapseSplit()
                        } else {
                            onClose?()
                        }
                    } label: {
                        Image(systemName: "xmark")
                            .font(.caption.weight(.semibold))
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel(isInSplit ? "Close this split" : "Close pane")
                    .help(isInSplit ? "Close this split" : "Close this pane")
                    Divider().frame(height: PaneHeadMetrics.dividerHeight)
                }
                selector()
            }
        }
    }

    /// Adaptive (ruling 2026-08-23): the full chain when the pane is wide
    /// enough, ONLY the leaf when it isn't — never a mid-string ellipsis.
    /// Right-click always shows the FULL path (so the collapsed form loses
    /// nothing); segments navigate on click and list their children as a
    /// menu, Xcode jump-bar style. `.layoutPriority` keeps the crumb from
    /// being squeezed to nothing by the fixed capsules on either side.
    @ViewBuilder
    private var breadcrumbCapsule: some View {
        if !crumbs.isEmpty {
            capsule {
                ViewThatFits(in: .horizontal) {
                    fullCrumbRow
                    // Middle rung (Daniel, 2026-08-23): ancestors collapse to
                    // their ICONS before the chain collapses to the leaf.
                    iconOnlyCrumbRow
                    crumbSegment(crumbs[crumbs.count - 1], isLeaf: true)
                }
                .accessibilityLabel(crumbs.map(\.name).joined(separator: ", "))
            }
            .contextMenu {
                // The whole ancestry, top-down — reachable even when the
                // capsule has collapsed to the leaf.
                ForEach(crumbs) { crumb in
                    Button {
                        onCrumb?(crumb)
                    } label: {
                        Label(crumb.name, systemImage: crumb.icon)
                    }
                    .disabled(onCrumb == nil || !crumb.isNavigable)
                }
            }
            .layoutPriority(1)
        }
    }

    private var fullCrumbRow: some View {
        HStack(spacing: 4) {
            ForEach(Array(crumbs.enumerated()), id: \.element.id) { index, crumb in
                if index > 0 {
                    Text("›").font(.callout).foregroundStyle(.secondary)
                }
                crumbSegment(crumb, isLeaf: index == crumbs.count - 1)
            }
        }
    }

    /// Ancestors as coloured icons only, the leaf keeping its name — the
    /// degradation rung between the full chain and leaf-only.
    private var iconOnlyCrumbRow: some View {
        HStack(spacing: 3) {
            ForEach(Array(crumbs.enumerated()), id: \.element.id) { index, crumb in
                if index > 0 {
                    Text("›").font(.caption).foregroundStyle(.secondary)
                }
                if index == crumbs.count - 1 {
                    crumbSegment(crumb, isLeaf: true)
                } else if let onCrumb, crumb.isNavigable {
                    Button { onCrumb(crumb) } label: {
                        Image(systemName: crumb.icon).foregroundStyle(crumb.tint)
                    }
                    .buttonStyle(.borderless)
                    .help(crumb.name)
                    .accessibilityLabel(crumb.name)
                } else {
                    Image(systemName: crumb.icon)
                        .foregroundStyle(crumb.tint)
                        .help(crumb.name)
                        .accessibilityLabel(crumb.name)
                }
            }
        }
    }

    /// One crumb. With navigation wired: a menu of the node's children
    /// (click = go there), whose primary click navigates to the node itself —
    /// the Xcode jump bar. Without children: a plain navigate button. Without
    /// wiring: text.
    @ViewBuilder
    private func crumbSegment(_ crumb: PaneCrumb, isLeaf: Bool) -> some View {
        // Icon carries the row's sidebar colour; only the TEXT dims on
        // ancestors — the coloured glyph is what makes the node recognisable.
        let label = HStack(spacing: 4) {
            Image(systemName: crumb.icon)
                .foregroundStyle(crumb.tint)
            Text(crumb.name)
                .foregroundStyle(isLeaf ? AnyShapeStyle(.primary) : AnyShapeStyle(.secondary))
        }
            .font(.callout)
            .lineLimit(1)
        if let onCrumb, crumb.isNavigable {
            let children = crumbChildren?(crumb) ?? []
            if children.isEmpty {
                Button { onCrumb(crumb) } label: { label }
                    .buttonStyle(.borderless)
                    .help("Go to \(crumb.name)")
            } else {
                Menu {
                    ForEach(children) { child in
                        Button {
                            onCrumb(child)
                        } label: {
                            Label(child.name, systemImage: child.icon)
                        }
                    }
                } label: {
                    label
                } primaryAction: {
                    onCrumb(crumb)
                }
                .menuStyle(.borderlessButton)
                .fixedSize()
                .help("Go to \(crumb.name) — hold for its contents")
            }
        } else {
            label
        }
    }

    private var controlsCapsule: some View {
        capsule {
            HStack(spacing: 6) {
                controls()
                // Shared chrome, automatic: split "+" (from the environment)
                // and the pin menu (when the pane supplies its state).
                PaneChromeMenu(splitActions: splitAxisActions, isPinned: isPinned)
                if Tools.self != EmptyView.self {
                    Divider().frame(height: PaneHeadMetrics.dividerHeight)
                    Button {
                        withAnimation(.snappy(duration: 0.16)) { showsTools.toggle() }
                    } label: {
                        Image(systemName: "ellipsis")
                    }
                    .buttonStyle(.borderless)
                    .accessibilityLabel(showsTools ? "Hide tools" : "Show tools")
                    .help(showsTools ? "Hide the tools row" : "Show the tools row")
                }
            }
        }
    }

    /// ONE capsule treatment, so every zone reads as the same material floating
    /// over the content rather than three different chrome ideas. Native Tahoe
    /// glass (S1, 2026-08-23): `.glassEffect` like every other floating bar
    /// (BottomActionBar, MiniToolbar) — the opaque `.regularMaterial` + stroke
    /// read as "too large, not translucent, not standard".
    private func capsule<Content: View>(@ViewBuilder _ content: () -> Content) -> some View {
        content()
            .padding(.horizontal, PaneHeadMetrics.capsulePadding)
            .padding(.vertical, PaneHeadMetrics.capsuleVerticalPadding)
            .glassEffect(.regular, in: Capsule())
    }
}

/// Shared metrics — one place, so the capsules cannot drift apart.
enum PaneHeadMetrics {
    static let inset: CGFloat = 8
    /// Trailing edge clears the scroll bar (Daniel, 2026-08-23).
    static let trailingInset: CGFloat = 20
    static let rowSpacing: CGFloat = 6
    static let capsuleSpacing: CGFloat = 8
    static let capsulePadding: CGFloat = 8
    static let capsuleVerticalPadding: CGFloat = 3
    static let dividerHeight: CGFloat = 14
}

extension PaneCrumb {
    /// The face a document wears everywhere — matches the sidebar/library rows
    /// so a crumb is recognisably the same node (Daniel, 2026-08-23).
    static func icon(for doc: Document) -> String {
        if doc.docType == .folder { return doc.isWorkspace ? "square.grid.2x2" : "folder" }
        if doc.docType == .page { return doc.fileType == .image ? "photo" : "doc.richtext" }
        if doc.fileType == .pdf { return "doc.richtext" }
        if doc.fileType == .image { return "photo" }
        return "doc.text"
    }

    /// Sidebar colour rules: containers wear the accent, leaves stay quiet.
    static func tint(for doc: Document) -> Color {
        doc.docType == .folder || doc.isWorkspace ? .accentColor : .secondary
    }

    init(_ doc: Document) {
        self.init(
            id: doc.id,
            name: DocumentTitle.displayName(for: doc),
            icon: Self.icon(for: doc),
            tint: Self.tint(for: doc)
        )
    }
}
