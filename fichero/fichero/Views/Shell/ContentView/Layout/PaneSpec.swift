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
    /// The centre row's panes. Which panes exist + their order now come from the
    /// F7 `PaneList` model (`PaneList.fromVisibility`) — the single, mode-independent
    /// source of truth — and this maps each pane KIND to its PaneSpec width. Behaviour
    /// is identical to the old plan-branched build (same panes, same order, same
    /// widths); this just routes "which panes" through the pane-list model so the
    /// renderer and the model agree, ahead of the full one-renderer step (spec §F7).
    ///
    /// Reading's presence matches the plan's own rule: it rides after the preview
    /// (`showsCanvasReadingDivider`) when a preview is up, else it stands alone
    /// (`showsReadingPane`). Chat is NOT a centre pane (panes.chat.below-sidebar) —
    /// it lives beneath the sidebar — so it is never in this list.
    var widescreenPaneSpecs: [PaneSpec] {
        let plan = adaptiveWidescreenPanePlan
        let readingPresent = plan.showsCanvasPane ? plan.showsCanvasReadingDivider : plan.showsReadingPane
        let list = PaneList.fromVisibility(
            library: plan.showsLibraryPane,
            preview: plan.showsCanvasPane,
            reading: readingPresent,
            chat: false
        )
        let kinds = list.nodes.compactMap { node -> PaneKind? in
            if case let .leaf(_, kind, _, _) = node { return kind }
            return nil
        }
        let hasPreview = kinds.contains(.preview)
        let hasReading = kinds.contains(.reading)
        return kinds.enumerated().map { index, kind in
            // `slot: index` gives each pane a position-unique id, so its split state and the
            // split-command routing key are per-instance, not shared across same-kind panes.
            switch kind {
            case .library:
                // list-only is full width; a fixed column only when a reading
                // surface shares the row (#1516 / #2006).
                let fixed: CGFloat? = (hasPreview || hasReading) ? clampedWidescreenContentPaneWidth : nil
                return PaneSpec(kind: .library, fixedWidth: fixed, slot: index)
            case .preview:
                return PaneSpec(kind: .preview, fixedWidth: nil, slot: index)
            case .reading:
                // A width only when it rides after a preview; standalone = full.
                return PaneSpec(kind: .reading, fixedWidth: hasPreview ? CGFloat(pageContentPaneWidth) : nil, slot: index)
            case .inspector:
                // Docks right, full height, flexible — no fixed column.
                return PaneSpec(kind: .inspector, fixedWidth: nil, slot: index)
            case .chat:
                return PaneSpec(kind: .chat, fixedWidth: nil, slot: index)  // not reached — chat is not in the list
            }
        }
    }

    /// `slotId` survives a kind override (2026-08-24): the split state is
    /// keyed "<slot>-<kind>", so two slots hosting the SAME kind split
    /// independently — the per-window "canvas" key made splitting one
    /// preview split both.
    private func kindContent(
        kind: PaneSpec.Kind, slotId: String, fixedWidth: CGFloat?
    ) -> AnyView {
        let spec = PaneSpec(kind: kind, fixedWidth: fixedWidth)
        let splitKey = "\(slotId)-\(kind.rawValue)"
        switch spec.kind {
        case .library:
            return AnyView(
                // Splittable (h/v) Library list pane — #2276.
                adaptiveSplittablePane(storageKey: splitKey) {
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
                widescreenCanvasPane(splitKey: splitKey)
                    .simultaneousGesture(
                        TapGesture().onEnded { _ in focusedPane = .preview; paneFocusHint = .preview }
                    )
            )
        case .reading:
            let reading = widescreenReadingPane(splitKey: splitKey)
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
                    closeLeaf: { id in activePaneList = activePaneList.removingLeaf(id) },
                    changeKind: { id, kind in activePaneList = activePaneList.changingLeafKind(id, to: kind) }
                ),
                extent: extents[index]
            )
        }
        WorkspaceSplitStack(axis: .horizontal, storageKey: "root", children: columns)
    }

    /// Render one node. AnyView because the recursion (node → split → node) can't ride an
    /// opaque `some View` return, and erasing at the boundary is the #4331 crash guard anyway.
    private func paneNodeView(
        _ node: PaneNode, keyPath: String, secondaryIDs: Set<UUID> = [], isSole: Bool = false,
        closeLeaf: ((UUID) -> Void)? = nil,
        changeKind: ((UUID, PaneKind) -> Void)? = nil
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
                    fixedWidth: nil
                )
                .environment(\.isSecondarySplitPane, secondaryIDs.contains(id))
                // Sole pane → the head collapses its close affordance (spec panes.head.sole-collapse).
                .environment(\.isSolePane, isSole)
                // Per-kind accessibility identifier so design-lead tests can assert exactly which
                // panes a workspace mounts (spec §Accessibility; WorkspaceAccessibilityUITests):
                // "pane.library" / "pane.preview" / "pane.reading" / "pane.inspector" / "pane.chat".
                .accessibilityIdentifier("pane.\(kind.rawValue)")
                // An applied pane is a HOSTING BOUNDARY: the window/app objects injected upstream
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
            return leaf
        case let .split(_, axis, children):
            return paneSplitView(
                axis: axis, children: children, keyPath: keyPath,
                secondaryIDs: secondaryIDs, closeLeaf: closeLeaf, changeKind: changeKind
            )
        }
    }

    /// A split node: children laid out along the axis in a RESIZABLE `WorkspaceSplitStack`, so every
    /// split in an applied workspace can be dragged (widths for a horizontal split, heights for a
    /// vertical one). Extents persist per split position via the `keyPath` storage key.
    private func paneSplitView(
        axis: SplitAxis, children: [PaneNode], keyPath: String,
        secondaryIDs: Set<UUID> = [], closeLeaf: ((UUID) -> Void)? = nil,
        changeKind: ((UUID, PaneKind) -> Void)? = nil
    ) -> AnyView {
        let extents = childExtents(children, axis: axis)
        let views = children.enumerated().map { idx, child in
            WorkspaceSplitStack.Child(
                paneNodeView(
                    child, keyPath: "\(keyPath).\(idx)",
                    secondaryIDs: secondaryIDs, closeLeaf: closeLeaf, changeKind: changeKind
                ),
                extent: extents[idx]
            )
        }
        return AnyView(WorkspaceSplitStack(axis: axis, storageKey: keyPath, children: views))
    }

    /// Per-child extent for a split's children (nil = FLEX): a child whose leaf declares
    /// `PaneConfig.paneExtent` (a film strip) is pinned to that size and the FIRST non-pinned child
    /// flexes; with no pinned child, the LAST child flexes and the earlier ones are resizable columns
    /// at a default extent. This is what makes the Transcribe/Compare library strip stay narrow while
    /// the page/reader above fill (CD 2026-09-16), without a strip elsewhere shrinking a real column.
    private func childExtents(_ nodes: [PaneNode], axis: SplitAxis) -> [Double?] {
        let pins: [Double?] = nodes.map { node in
            if case let .leaf(_, _, _, config) = node { return config.paneExtent }
            return nil
        }
        let defaultExtent: Double = axis == .horizontal ? 360 : 300
        if pins.contains(where: { $0 != nil }) {
            let flexIndex = pins.firstIndex { $0 == nil } ?? 0
            return nodes.indices.map { idx in pins[idx] ?? (idx == flexIndex ? nil : defaultExtent) }
        }
        let last = nodes.count - 1
        return nodes.indices.map { idx in idx == last ? nil : defaultExtent }
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
