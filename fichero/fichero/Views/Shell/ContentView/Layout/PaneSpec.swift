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
    enum Kind: String {
        case library
        case preview
        case reading
        case chat
    }

    let kind: Kind
    /// Fixed width when a divider governs this pane; nil = flexible.
    var fixedWidth: CGFloat?

    var id: String { kind.rawValue }
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
    private func paneContent(for spec: PaneSpec) -> AnyView {
        switch spec.kind {
        case .library:
            return AnyView(
                // Splittable (h/v) Library list pane — #2276.
                adaptiveSplittablePane(storageKey: "library") {
                    contentWithOptionalModeRail
                }
                .frame(width: spec.fixedWidth)
                .frame(maxWidth: spec.fixedWidth == nil ? .infinity : nil)
                // The library pane must never paint past its own split
                // column — otherwise list/grid rows can bleed under the
                // shell sidebar or off the left window edge.
                .clipped()
                .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .content; paneFocusHint = .content })
                .overlay { paneFocusIndicator(for: .content) }
            )
        case .preview:
            return AnyView(widescreenCanvasPane)
        case .reading:
            if let width = spec.fixedWidth {
                return AnyView(widescreenReadingPane.frame(width: width))
            }
            return AnyView(widescreenReadingPane.frame(maxWidth: .infinity))
        case .chat:
            return AnyView(
                chatPaneContent
                    .frame(width: spec.fixedWidth ?? CGFloat(ContentView.chatPaneMinWidth))
                    .simultaneousGesture(TapGesture().onEnded { _ in focusedPane = .chat; paneFocusHint = .chat })
                    .overlay { paneFocusIndicator(for: .chat) }
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
            onConversationUpdated: { refreshConversations() }
        )
    }
}
