import SwiftUI

// MARK: - Chat mount decision (spec panes.chat.below-sidebar)

/// Pure decision for WHICH conversation the chat surface shows — extracted so
/// it is unit-testable without a running view. The chat surface (now beneath the
/// sidebar, `ContentView.chatSurface`) follows the view mode: a selected chat
/// names its conversation, anything else is a fresh one.
enum ChatMount {
    static func conversation(for viewMode: AppViewMode) -> Conversation? {
        if case .chat(let conversation) = viewMode { return conversation }
        return nil
    }
}

// MARK: - Pane system, step 1 (#13 / pane-system-proposal-2026-08-11)

/// One pane of the widescreen centre row.
///
/// Step 1 of the pane-system migration: the row is rendered from a LIST of
/// these instead of the hand-branched HStack in `centerContentRouting` —
/// behavior-identical (the list is still derived from `WidescreenPanePlan`,
/// not yet persisted or reorderable), but the shape is the one chat and the
/// terminal drawer extend by ADDING SPECS, and every pane is erased at its
/// own boundary, which is what caps the composed-generic crash class
/// (#4331: four incidents on 2026-08-11 alone, all rooted in this routing's
/// branch product type).
struct PaneSpec: Identifiable, Equatable {
    enum Kind: String, CaseIterable {
        case library
        case preview
        case reading
        case inspector
        case chat

        var title: String {
            switch self {
            case .library: "Library"
            case .preview: "Preview"
            case .reading: "Reader"
            case .inspector: "Inspector"
            case .chat: "Chat"
            }
        }

        var icon: String {
            switch self {
            case .library: "books.vertical"
            case .preview: "photo"
            case .reading: "book"
            case .inspector: "sidebar.trailing"
            case .chat: "bubble.left.and.bubble.right"
            }
        }

        /// The kinds a pane can actually be switched TO. `.inspector` and
        /// `.chat` stay in `Kind`/`allCases` so the switcher's model type is
        /// total (`PaneKindSwitcher`, `kindContent(kind:...)`), but both are
        /// placeholder leaves today (`kindContent`'s `.inspector`/`.chat`
        /// arms render `PaneEmptyStateView`, not real content) — offering
        /// them in the kind-switch menu would let a click "switch" a pane to
        /// a dead end. Ship them here only when #4705 increments 6 (chat as
        /// a movable pane) / 7 (inspector as a real leaf) give them content.
        static var selectableKinds: [Kind] {
            allCases.filter { $0 != .inspector && $0 != .chat }
        }
    }

    let kind: Kind
    /// Fixed width when a divider governs this pane; nil = flexible.
    var fixedWidth: CGFloat?
    /// The pane's POSITION in the row. This is what makes the slot id — and therefore the split
    /// @SceneStorage and the split-command routing key — per-INSTANCE instead of per-KIND. Before
    /// this, `id == kind.rawValue`, so two panes of the same kind shared one split cell and one
    /// broadcast match: splitting/closing one hit them all (spec CD 2026-09-15,
    /// panes.split.focused-only). Position-scoping isolates each pane.
    var slot: Int = 0

    var id: String { "\(slot)-\(kind.rawValue)" }
}

/// Injected per pane SLOT so the head's kind icon can switch what the slot
/// hosts (Daniel, 2026-08-23: "clicking on the view type icon should let us
/// change what it is"). nil = the pane is not hosted in a switchable slot.
///
/// EQUATABLE BY SLOT ID (2026-08-24, the morning slowness): a bare closure
/// in the environment is never equal to itself, so every parent render read
/// as an environment CHANGE and re-walked the whole pane subtree — the
/// EnvironmentBox/copyItems stall storm in the live log. The closure
/// captures only the slot id, so identity by id is exact.
struct PaneKindSwitcher: Equatable {
    let slotId: String
    let switchKind: @MainActor (PaneSpec.Kind) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.slotId == rhs.slotId }
}

private struct PaneKindSwitcherKey: EnvironmentKey {
    static let defaultValue: PaneKindSwitcher? = nil
}

extension EnvironmentValues {
    var paneKindSwitcher: PaneKindSwitcher? {
        get { self[PaneKindSwitcherKey.self] }
        set { self[PaneKindSwitcherKey.self] = newValue }
    }
}

/// Injected per pane SLOT (library leaves only) so the pane-head content-kind
/// chip (Documents/Claims/Entities) can set an EXPLICIT, SAVED kind for THIS
/// pane (#4884) — `PaneList.changingLeafContentKind`, not `LibraryView`'s
/// local `@State`. nil = this Library pane is not hosted in a switchable slot
/// (the compact iPhone reader stack's leaf, which sits outside the pane tree
/// entirely — `LibraryView.libraryContentKind` is that leaf's own fallback).
///
/// EQUATABLE BY SLOT ID ONLY — same reason as `PaneKindSwitcher` above (a bare
/// closure is never `==` itself, which re-walks the whole pane subtree on
/// every parent render).
struct PaneContentKindSwitcher: Equatable {
    let slotId: String
    let switchContentKind: @MainActor (LibraryContentKind?) -> Void

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.slotId == rhs.slotId }
}

private struct PaneContentKindSwitcherKey: EnvironmentKey {
    static let defaultValue: PaneContentKindSwitcher? = nil
}

private struct PaneContentKindKey: EnvironmentKey {
    static let defaultValue: LibraryContentKind? = nil
}

extension EnvironmentValues {
    var paneContentKindSwitcher: PaneContentKindSwitcher? {
        get { self[PaneContentKindSwitcherKey.self] }
        set { self[PaneContentKindSwitcherKey.self] = newValue }
    }

    /// The EXPLICIT content kind a workspace/user set for THIS library pane
    /// (`PaneConfig.libraryContentKind`, decoded), published by
    /// `ContentView.paneNodeView` — mirrors `\.paneLibraryLayout`'s shape
    /// exactly (`ViewDisplayMode.swift`), the same mechanism for the sibling
    /// per-pane-config field. nil everywhere outside a library leaf's own
    /// slot, or when that leaf has never had an explicit kind set.
    var paneContentKind: LibraryContentKind? {
        get { self[PaneContentKindKey.self] }
        set { self[PaneContentKindKey.self] = newValue }
    }
}

private struct IsSolePaneKey: EnvironmentKey {
    static let defaultValue = false
}

extension EnvironmentValues {
    /// True when this pane is the window's ONLY pane — the head then collapses its close affordance
    /// (nothing to close; the ≥1-pane invariant), so a single pane wears the least chrome (CD
    /// 2026-09-16: "collapse better if there is just one").
    var isSolePane: Bool {
        get { self[IsSolePaneKey.self] }
        set { self[IsSolePaneKey.self] = newValue }
    }
}

extension ContentView {
    /// `slotId` survives a kind override (2026-08-24): the split state is
    /// keyed "<slot>-<kind>", so two slots hosting the SAME kind split
    /// independently — the per-window "canvas" key made splitting one
    /// preview split both.
    private func kindContent(
        kind: PaneSpec.Kind, slotId: String, fixedWidth: CGFloat?,
        splitLeaf: ((SplitAxis) -> Void)? = nil
    ) -> AnyView {
        let spec = PaneSpec(kind: kind, fixedWidth: fixedWidth)
        let splitKey = "\(slotId)-\(kind.rawValue)"
        let modelSplit = splitLeaf.map { PaneModelSplitHook(split: $0) }
        switch spec.kind {
        case .library:
            return AnyView(
                // Splittable (h/v) Library list pane — #2276.
                adaptiveSplittablePane(storageKey: splitKey, modelSplit: modelSplit) {
                    contentWithOptionalModeRail
                }
                .frame(width: spec.fixedWidth)
                .frame(maxWidth: spec.fixedWidth == nil ? .infinity : nil)
                // The library pane must never paint past its own split
                // column — otherwise list/grid rows can bleed under the
                // shell sidebar or off the left window edge.
                .clipped()
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content; paneFocusHint = .content })
            )
        case .preview:
            // Clicking a pane FOCUSES it — the same gesture .content and .chat
            // already carried. Without it the focus hint never left .content,
            // so ⌘A over a clicked preview still went to the library (Daniel,
            // live 2026-08-23).
            return AnyView(
                widescreenCanvasPane(splitKey: splitKey, modelSplit: modelSplit)
                    .simultaneousGesture(
                        TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview }
                    )
            )
        case .reading:
            let reading = widescreenReadingPane(splitKey: splitKey, modelSplit: modelSplit)
                .simultaneousGesture(
                    TapGesture().onEnded { _ in focusedPane = .reading; paneFocusHint = .reading }
                )
            if let width = spec.fixedWidth {
                return AnyView(reading.frame(width: width))
            }
            return AnyView(reading.frame(maxWidth: .infinity))
        case .inspector:
            // The document inspector as a CENTRE PANE (spec §"v2 workspaces": the inspector
            // docks in the pane list, always on the right). Reserving the kind so workspaces can
            // compose it and the model stays total; hosting the real InspectorView content here
            // is the next increment (it needs the selected document + service environment, the
            // same boundary the sidebar chat re-injects).
            return AnyView(
                PaneEmptyStateView(reason: "Inspector")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .inspector; paneFocusHint = .inspector })
            )
        case .chat:
            // Chat is no longer a centre pane — it lives beneath the sidebar
            // (spec panes.chat.below-sidebar). The kind stays in the enum so the
            // slot switcher's `Kind` type stays total, but a slot manually
            // switched to Chat now points the user to its real home instead of
            // mounting a SECOND `ChatView` — a second one would carry its own
            // @State conversation (double-send). The one mount is `chatSurface`
            // in ContentView.sidebarContent.
            return AnyView(
                PaneEmptyStateView(reason: "Chat lives beneath the sidebar.")
                    .frame(maxWidth: .infinity)
                    .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .chat; paneFocusHint = .chat })
            )
        }
    }

    // MARK: - The ONE renderer (spec §F7: one rendering path)

    /// Map the pure-model `PaneKind` to the view's `PaneSpec.Kind`. They carry the same four
    /// cases today; this is the seam where the F2 vocabulary unification lands.
    private func paneSpecKind(_ kind: PaneKind) -> PaneSpec.Kind {
        switch kind {
        case .library: .library
        case .preview: .preview
        case .reading: .reading
        case .inspector: .inspector
        case .chat: .chat
        }
    }

    /// The inverse of `paneSpecKind` — the head's kind menu delivers a `PaneSpec.Kind`, which the
    /// applied-path kind-switch turns back into a model `PaneKind` to mutate the leaf.
    private func paneKind(_ specKind: PaneSpec.Kind) -> PaneKind {
        switch specKind {
        case .library: .library
        case .preview: .preview
        case .reading: .reading
        case .inspector: .inspector
        case .chat: .chat
        }
    }

    /// Render an APPLIED workspace pane list — every level through the recursive node renderer
    /// (top-level nodes lay out as a horizontal row; a split arranges its children along its
    /// axis), so a STORED `PaneList` (`activePaneList`) is the source of truth. Unlike
    /// `paneComposition`, this never delegates the multi-pane row to `widescreenPaneRow` (which
    /// reads the legacy visibility plan) — the applied list is authoritative.
    /// ponytail: equal-flex panes, no resizable dividers/fixed widths yet; porting
    /// `widescreenPaneRow`'s width+divider logic here is the follow-up that retires the second
    /// renderer. Each top-level node is keyed by its index so its split state stays per-instance.
    @ViewBuilder
    func paneListRow(_ list: PaneList) -> some View {
        // A window-scoped focused value admits ONE publisher per key: a workspace with two
        // same-kind panes (Compare) must flag every duplicate SECONDARY so it doesn't co-publish
        // and loop the scene graph (spec panes.instance-safe). Computed once, from the list shape.
        let secondaryIDs = list.secondaryLeafIDs()
        // The top-level columns, as RESIZABLE widths (WorkspaceSplitStack) — the applied-workspace
        // path is now fully resizable (CD 2026-09-16). Closing a pane removes THIS leaf from the
        // stored list (spec panes.close.this-pane-only); @State's nonmutating setter makes capturing
        // self safe.
        let solePane = list.leafCount == 1
        let extents = childExtents(list.nodes, axis: .horizontal)
        let columns = list.nodes.enumerated().map { index, node in
            WorkspaceSplitStack.Child(
                paneNodeView(
                    node, keyPath: "\(index)", secondaryIDs: secondaryIDs, isSole: solePane,
                    closeLeaf: { id in
                        activePaneList = activePaneList.removingLeaf(id)
                        paneListDidChange()
                    },
                    changeKind: { id, kind in
                        activePaneList = activePaneList.changingLeafKind(id, to: kind)
                        paneListDidChange()
                    },
                    changeContentKind: { id, contentKind in
                        activePaneList = activePaneList.changingLeafContentKind(id, to: contentKind?.rawValue)
                        paneListDidChange()
                    },
                    // ONE CODE PATH (2026-09-20 ruling): the in-pane split control
                    // (`SplittablePane`'s `\.splitAxisActions`, surfaced via
                    // `PaneChromeMenu`'s "+") now calls THIS — the same
                    // `PaneList.splittingLeaf` the Workspaces menu already uses —
                    // instead of duplicating this leaf's own rendered content.
                    splitLeaf: { id, axis in
                        activePaneList = activePaneList.splittingLeaf(id, axis: axis)
                        paneListDidChange()
                    }
                ),
                sizing: extents[index]
            )
        }
        // The leading node's own id makes the key workspace-unique (#4688): a bare "root" (or a
        // tree-position string) is the SAME for every applied workspace, so Read's inner split and
        // Transcribe's film strip — both at position "0" — shared one @SceneStorage slot. A node's
        // id is fresh per applied `PaneList`, so two different workspaces' top-level rows never
        // collide even though they're both "root".
        let storageKey = WorkspaceSplitStack.storageKey(keyPath: "root", leadingChildID: list.nodes.first?.id)
        WorkspaceSplitStack(axis: .horizontal, storageKey: storageKey, children: columns)
    }

    /// Render one node. AnyView because the recursion (node → split → node) can't ride an
    /// opaque `some View` return, and erasing at the boundary is the #4331 crash guard anyway.
    private func paneNodeView(
        _ node: PaneNode, keyPath: String, secondaryIDs: Set<UUID> = [], isSole: Bool = false,
        closeLeaf: ((UUID) -> Void)? = nil,
        changeKind: ((UUID, PaneKind) -> Void)? = nil,
        changeContentKind: ((UUID, LibraryContentKind?) -> Void)? = nil,
        splitLeaf: ((UUID, SplitAxis) -> Void)? = nil
    ) -> AnyView {
        switch node {
        case let .leaf(id, kind, _, config):
            // kindContent already returns AnyView (head chrome + clip + focus gesture). A DUPLICATE
            // same-kind leaf renders secondary so its subtree suppresses the window-scoped
            // focused-value publishes the primary owns (spec panes.instance-safe); the flag is the
            // SAME `\.isSecondarySplitPane` an in-pane split already uses. On the applied path
            // `closeLeaf` also publishes this leaf's close action, so the head's X removes THIS pane
            // (spec panes.close.this-pane-only), not the whole row.
            var leaf = AnyView(
                kindContent(
                    kind: paneSpecKind(kind),
                    slotId: "pane-\(keyPath)-\(kind.rawValue)",
                    fixedWidth: nil,
                    // THIS leaf's own id, closed over here — the same per-leaf
                    // seam `changeKind`/`changeContentKind` already use, now
                    // extended to split (ONE CODE PATH ruling, 2026-09-20).
                    splitLeaf: splitLeaf.map { leafSplit in { axis in leafSplit(id, axis) } }
                )
                .environment(\.isSecondarySplitPane, secondaryIDs.contains(id))
                // Sole pane → the head collapses its close affordance (spec panes.head.sole-collapse).
                .environment(\.isSolePane, isSole)
                // Per-kind accessibility identifier so design-lead tests can assert exactly which
                // panes a workspace mounts (spec §Accessibility; WorkspaceAccessibilityUITests):
                // "pane.library" / "pane.preview" / "pane.reading" / "pane.inspector" / "pane.chat".
                .accessibilityIdentifier("pane.\(kind.rawValue)")
                // NOT a hosting boundary — corrected 2026-09-17. AnyView does not re-root the
                // environment, so this modifier is a no-op here (see
                // ContentView+WindowEnvironment for the evidence and the real cause). Kept
                // because re-injecting what is already in scope costs nothing.
                // Historical note, left because it explains the comment below: the window/app
                // objects injected upstream
                // (ContentView+Navigation, ContentView+RootLayout) do not reliably cross it, so a
                // pane's subtree can die on a non-optional @Environment read. Exactly the 2026-08-11
                // failure — "the horizontal library split's second pane died on
                // WorkflowExecutionObserver" — and the crash Daniel hit at launch once the Read
                // workspace began mounting a reader on startup (2026-09-17).
                // ALL of them, never a hand-picked list: re-injecting what is already in scope is a
                // no-op; omitting one is a trap. Same set the other two boundaries re-inject.
                //
                // 2026-09-17, second pass: this said "ALL" while injecting SEVEN. A workflow pane
                // reads WorkflowStore, which was not among them, so mounting one trapped in
                // EnvironmentValues.subscript.getter (EXC_BREAKPOINT) with no app frame in the
                // stack to name it. It now applies the ONE shared list
                // (ContentView+WindowEnvironment) so all three boundaries cannot diverge again.
                .modifier(windowEnvironment)
            )
            // The workspace's per-pane library layout (Read = table, Browse = icons, …): publish it
            // so THIS library pane renders in the workspace's mode instead of the window's global one
            // (spec §"v2 workspace design", per-pane config).
            if kind == .library,
               let raw = config.libraryLayout,
               let mode = ViewDisplayMode(paneLibraryLayout: raw) {
                leaf = AnyView(leaf.environment(\.paneLibraryLayout, mode))
            }
            // The workspace/chip-set EXPLICIT content kind for THIS library pane
            // (#4884) — mirrors the libraryLayout block immediately above,
            // same seam shape for the sibling PaneConfig field.
            if kind == .library, let raw = config.libraryContentKind,
               let contentKind = LibraryContentKind(rawValue: raw) {
                leaf = AnyView(leaf.environment(\.paneContentKind, contentKind))
            }
            if let closeLeaf {
                leaf = AnyView(leaf.environment(\.paneCloseAction, PaneCloseAction { closeLeaf(id) }))
            }
            // The head's far-left kind menu (`PaneKindSelector`) is inert until a `\.paneKindSwitcher`
            // is present. Inject it on the applied path so switching a pane's kind mutates THIS leaf
            // in the stored list (spec panes.head.kind-switch) — the same per-leaf seam as close.
            if let changeKind {
                let switcher = PaneKindSwitcher(slotId: "pane-\(keyPath)-\(kind.rawValue)") { specKind in
                    changeKind(id, paneKind(specKind))
                }
                leaf = AnyView(leaf.environment(\.paneKindSwitcher, switcher))
            }
            // The pane-head content-kind chip (#4884) is inert until a
            // `\.paneContentKindSwitcher` is present — same shape as the kind
            // switcher above, scoped to `.library` leaves only.
            if kind == .library, let changeContentKind {
                let contentSwitcher = PaneContentKindSwitcher(
                    slotId: "pane-\(keyPath)-\(kind.rawValue)"
                ) { newContentKind in
                    changeContentKind(id, newContentKind)
                }
                leaf = AnyView(leaf.environment(\.paneContentKindSwitcher, contentSwitcher))
            }
            return leaf
        case let .split(_, axis, children):
            return paneSplitView(
                axis: axis, children: children, keyPath: keyPath,
                secondaryIDs: secondaryIDs, closeLeaf: closeLeaf, changeKind: changeKind,
                changeContentKind: changeContentKind, splitLeaf: splitLeaf
            )
        }
    }

    /// A split node: children laid out along the axis in a RESIZABLE `WorkspaceSplitStack`, so every
    /// split in an applied workspace can be dragged (widths for a horizontal split, heights for a
    /// vertical one). Extents persist per split position via the `keyPath` storage key.
    private func paneSplitView(
        axis: SplitAxis, children: [PaneNode], keyPath: String,
        secondaryIDs: Set<UUID> = [], closeLeaf: ((UUID) -> Void)? = nil,
        changeKind: ((UUID, PaneKind) -> Void)? = nil,
        changeContentKind: ((UUID, LibraryContentKind?) -> Void)? = nil,
        splitLeaf: ((UUID, SplitAxis) -> Void)? = nil
    ) -> AnyView {
        let extents = childExtents(children, axis: axis)
        let views = children.enumerated().map { idx, child in
            WorkspaceSplitStack.Child(
                paneNodeView(
                    child, keyPath: "\(keyPath).\(idx)",
                    secondaryIDs: secondaryIDs, closeLeaf: closeLeaf, changeKind: changeKind,
                    changeContentKind: changeContentKind, splitLeaf: splitLeaf
                ),
                sizing: extents[idx]
            )
        }
        // Same workspace-unique-key fix as `paneListRow` (#4688): `keyPath` alone is a tree
        // POSITION, identical across every workspace, so two different workspaces' splits at the
        // same position collided. The leading child's own id (fresh per applied `PaneList`) makes
        // this key unique per workspace, not just per position.
        let storageKey = WorkspaceSplitStack.storageKey(keyPath: keyPath, leadingChildID: children.first?.id)
        return AnyView(WorkspaceSplitStack(axis: axis, storageKey: storageKey, children: views))
    }

    /// The whole-pane fixed extent for a `.library` leaf pinned via `paneExtent` (#4848,
    /// `panes.strip.fixed-extent-is-content-not-whole-pane`): `paneExtent` names the VISIBLE ICON
    /// STRIP height only (72pt, unchanged) — this adds the pane's OWN chrome (its head bar +
    /// its bottom mini-toolbar), which used to have nowhere to render because `paneExtent` was
    /// being treated as the extent of the WHOLE pane. Derived from the SAME metrics `PaneHead`
    /// and the library bottom bar actually render at (`PaneHeadMetrics.barHeight`,
    /// `MiniToolbar.standardHeight`) — not a second magic number.
    static func libraryStripExtent(iconStrip: Double) -> Double {
        iconStrip + PaneHeadMetrics.barHeight + MiniToolbar<EmptyView, EmptyView>.standardHeight
    }

    /// Per-child SIZING for a split's children: HARD-pinned (`PaneConfig.paneExtent` — the film
    /// strip, absolute points, ignores stored drag state), PROPORTIONAL (`PaneConfig.paneFraction`
    /// — a resizable column seeded from a fraction of the stack's own extent), or FLEX (fills
    /// whatever the sized/pinned siblings leave over). An extent always wins over a fraction on the
    /// same leaf (`Sizing.preferred`, pure + unit-tested). A `.library` leaf's `paneExtent` is
    /// widened to include its own chrome (`libraryStripExtent`, #4848) before `Sizing.preferred`
    /// ever sees it.
    private func childExtents(_ nodes: [PaneNode], axis: SplitAxis) -> [WorkspaceSplitStack.Sizing] {
        let preferences: [WorkspaceSplitStack.Sizing?] = nodes.map { node in
            guard case let .leaf(_, kind, _, config) = node else { return nil }
            let extent = config.paneExtent.map { kind == .library ? Self.libraryStripExtent(iconStrip: $0) : $0 }
            return WorkspaceSplitStack.Sizing.preferred(extent: extent, fraction: config.paneFraction)
        }
        return Self.childSizings(preferences, fallbackFraction: 0.4)
    }

    /// Pure (#4849, `panes.split.peers-open-even`): turn each child's own preference (an explicit
    /// pin/fraction, or `nil`) into its final `Sizing`, given the whole sibling set.
    ///
    /// A PEER is a child with NO explicit `paneExtent`/`paneFraction` of its own (a `nil`
    /// preference) — the definition team-lead proposed. Peers SHARE EVENLY whatever the explicit
    /// siblings (fractions and — via the existing sum-clamp in `WorkspaceSplitStack.resolvedExtents`
    /// — fixed pins) leave over: `(1 − sum of explicit fractions) / peer count`, not the old flat
    /// `fallbackFraction` every non-explicit child got regardless of how many peers there were
    /// (which made 2/3/4 peers come out unequal — two matched the flat fallback, only the LAST
    /// child ever truly flexed to the real remainder).
    ///
    /// One peer still gets `.flex` rather than `.fraction(peerShare)` — the same value as every
    /// other peer WHEN NO PIN IS PRESENT (the flex space left over is exactly `peerShare × total`,
    /// once every other peer and every explicit fraction sibling has taken its share, since
    /// `peerShare` is itself derived as a share of `total`) — but it keeps a genuine flex slot in
    /// the mix so the pane list always has somewhere that absorbs a total that doesn't divide
    /// evenly, and preserves which slot flexes today: the FIRST peer when a pin is present (the
    /// rule that keeps the Transcribe/Compare film strip pinned while the content above it fills
    /// the rest), the LAST peer when there is no pin (CD 2026-09-17's rule for the un-pinned
    /// workspaces). With a pin and no peer at all, nothing is left to flex — every child is
    /// either pinned or explicitly fractioned, so each just keeps its own preference.
    ///
    /// KNOWN LIMITATION, not exercised by any built-in and not part of #4849's reported shape
    /// (every built-in pairs a pin with exactly ONE peer, which is always correct): with a pin
    /// AND MORE THAN ONE peer in the same split, `peerShare` is computed as a fraction of the
    /// whole `total` — this function has no `total` to subtract the pin's absolute points from
    /// (that value is not known until `WorkspaceSplitStack`'s own `GeometryReader`, deliberately
    /// later than this pure, position-only decision) — so the non-flexing peers divide `total`
    /// evenly among themselves, but the ONE flexing peer additionally absorbs the pin's points and
    /// ends up smaller than its siblings by roughly the pin's size. Fixing this precisely would
    /// mean threading `total` all the way back to `childExtents`, called before it exists.
    static func childSizings(
        _ preferences: [WorkspaceSplitStack.Sizing?],
        fallbackFraction: Double
    ) -> [WorkspaceSplitStack.Sizing] {
        guard !preferences.isEmpty else { return [] }
        let isPinned: (WorkspaceSplitStack.Sizing?) -> Bool = { if case .fixed? = $0 { return true }; return false }
        let explicitFractionSum: Double = preferences.compactMap { pref -> Double? in
            if case let .fraction(fraction)? = pref { return fraction }
            return nil
        }.reduce(0, +)
        let peerIndices = preferences.indices.filter { preferences[$0] == nil }
        let peerShare = peerIndices.isEmpty
            ? fallbackFraction
            : max(0, 1 - explicitFractionSum) / Double(peerIndices.count)

        let hasPin = preferences.contains(where: isPinned)
        let flexIndex: Int? = hasPin ? peerIndices.first : peerIndices.last

        return preferences.indices.map { idx in
            if isPinned(preferences[idx]) { return preferences[idx]! }
            if let preference = preferences[idx] { return preference }
            if idx == flexIndex { return .flex }
            return .fraction(peerShare)
        }
    }

    /// The assistant chat surface — the SAME `ChatView` the old centre pane
    /// rendered, now mounted beneath the sidebar folder tree
    /// (spec panes.chat.below-sidebar). ONE mount definition, called from
    /// `ContentView.sidebarContent`. `internal` (not `private`) so that
    /// cross-file caller can reach it; conversation history is unchanged because
    /// it is backend-backed (ChatService/ConversationService), not view @State.
    @ViewBuilder
    var chatSurface: some View {
        ChatView(
            conversation: ChatMount.conversation(for: viewMode),
            selectedDocuments: $chatSelectedDocuments,
            attachContext: chatAttachContext,
            onConversationUpdated: { refreshConversations() },
            // X on the chat head hides the region — the toolbar toggle's seam.
            onClosePane: { setChatPaneVisible(false) }
        )
    }
}
