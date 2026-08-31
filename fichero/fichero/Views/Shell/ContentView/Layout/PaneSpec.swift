import SwiftUI

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
        case chat

        var title: String {
            switch self {
            case .library: "Library"
            case .preview: "Preview"
            case .reading: "Reader"
            case .chat: "Chat"
            }
        }

        var icon: String {
            switch self {
            case .library: "books.vertical"
            case .preview: "photo"
            case .reading: "book"
            case .chat: "bubble.left.and.bubble.right"
            }
        }
    }

    let kind: Kind
    /// Fixed width when a divider governs this pane; nil = flexible.
    var fixedWidth: CGFloat?

    var id: String { kind.rawValue }
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

extension ContentView {
    /// The centre row's panes, derived from the SAME plan the old HStack
    /// branched on — one place states which panes exist and how they size.
    var widescreenPaneSpecs: [PaneSpec] {
        let plan = adaptiveWidescreenPanePlan
        var specs: [PaneSpec] = []
        if plan.showsLibraryPane {
            // list-only is full width; a fixed column only when a reading
            // surface shares the row (#1516 / #2006).
            let fixed: CGFloat? = (plan.showsCanvasPane || plan.showsReadingPane)
                ? clampedWidescreenContentPaneWidth : nil
            specs.append(PaneSpec(kind: .library, fixedWidth: fixed))
        }
        if plan.showsCanvasPane {
            specs.append(PaneSpec(kind: .preview, fixedWidth: nil))
            if plan.showsCanvasReadingDivider {
                specs.append(PaneSpec(kind: .reading, fixedWidth: CGFloat(pageContentPaneWidth)))
            }
        } else if plan.showsReadingPane {
            specs.append(PaneSpec(kind: .reading, fixedWidth: nil))
        }
        if plan.showsChatPane {
            // Chat is the NARROW pane right of the reader (2026-08-11 pane
            // rulings) — a fixed column its divider drags, never a takeover.
            specs.append(PaneSpec(kind: .chat, fixedWidth: CGFloat(chatPaneWidth)))
        }
        return specs
    }

    /// The widescreen centre row, rendered from `widescreenPaneSpecs`.
    var widescreenPaneRow: some View {
        let specs = widescreenPaneSpecs
        return HStack(spacing: 0) {
            ForEach(Array(specs.enumerated()), id: \.element.id) { index, spec in
                if index > 0 {
                    paneDivider(between: specs[index - 1].kind, and: spec.kind)
                }
                paneContent(for: spec)
            }
        }
        .frame(maxWidth: .infinity)
    }

    /// The divider (if any) between two adjacent panes. The library's
    /// divider drags the library column (`widescreenContentPaneWidth`); the
    /// preview↔reading divider drags the reading column
    /// (`pageContentPaneWidth`) — the same two bindings the old HStack wired.
    @ViewBuilder
    private func paneDivider(between leading: PaneSpec.Kind, and trailing: PaneSpec.Kind) -> some View {
        switch (leading, trailing) {
        case (.library, _):
            ResizableDivider(
                width: $widescreenContentPaneWidth,
                minWidth: ContentView.contentListMinWidth,
                maxWidth: 900,
                edge: .leading,
                isDragging: $dividerDragInFlight
            )
        case (.preview, .reading):
            ResizableDivider(
                width: $pageContentPaneWidth,
                minWidth: ContentView.readingPaneMinWidth,
                maxWidth: 900,
                edge: .trailing,
                isDragging: $dividerDragInFlight
            )
        case (_, .chat):
            ResizableDivider(
                width: $chatPaneWidth,
                minWidth: ContentView.chatPaneMinWidth,
                maxWidth: 700,
                edge: .trailing,
                isDragging: $dividerDragInFlight
            )
        default:
            EmptyView()
        }
    }

    /// One pane's content — AnyView by construction: each pane's generic
    /// ends at its own boundary instead of multiplying into the row's.
    /// The SLOT's kind can be overridden (Daniel, 2026-08-23): any slot can
    /// host any pane kind, switched from its head's kind icon; multiple
    /// instances of a kind may coexist.
    private func paneContent(for spec: PaneSpec) -> AnyView {
        let effectiveKind = paneKindOverrides[spec.id] ?? spec.kind
        return AnyView(
            kindContent(kind: effectiveKind, slotId: spec.id, fixedWidth: spec.fixedWidth)
                .environment(\.paneKindSwitcher, PaneKindSwitcher(slotId: spec.id) { newKind in
                    paneKindOverrides[spec.id] = newKind == spec.kind ? nil : newKind
                })
        )
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
        case .chat:
            // Splittable like every other pane (Daniel, 2026-08-29: "some
            // panes offer splits and chat does not") — the SAME machinery,
            // so the toolbar's Split Right/Below reaches a focused chat too.
            return AnyView(
                adaptiveSplittablePane(storageKey: splitKey) {
                    chatPaneContent
                }
                .frame(width: spec.fixedWidth ?? CGFloat(ContentView.chatPaneMinWidth))
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .chat; paneFocusHint = .chat })
            )
        }
    }

    /// The row's chat pane — the SAME ChatView the old takeover mode
    /// rendered, scoped by the same attach context, just living beside the
    /// reader instead of over everything. While the sidebar has a chat
    /// selected, the pane follows it; otherwise it is a fresh conversation.
    @ViewBuilder
    private var chatPaneContent: some View {
        ChatView(
            conversation: {
                if case .chat(let conversation) = viewMode { return conversation }
                return nil
            }(),
            selectedDocuments: $chatSelectedDocuments,
            attachContext: chatAttachContext,
            onConversationUpdated: { refreshConversations() },
            // X on the chat head hides the pane — the toolbar toggle's seam.
            onClosePane: { setChatPaneVisible(false) }
        )
    }
}
