import OSLog
import SwiftUI

private let logger = Logger(subsystem: "app.fichero.fichero", category: "SidebarModeBar")

/// Xcode-style mode icon bar at the top of the sidebar.
/// Shows mode icons for the enabled sidebar modes.
struct SidebarModeBar: View {
    @Binding var selectedMode: SidebarMode

    // Feature manager to hide disabled modes
    @Environment(FeatureManager.self) var featureManager

    /// Fallback icon budget: how many mode icons render inline before the rest
    /// collapse into the '…' overflow (#3059). Selected + `.library` are always
    /// kept inline on top of this, so a narrow sidebar never loses context.
    private let compactInlineLimit = 4

    var body: some View {
        // Modern translucent Liquid Glass background, matching SidebarBottomToolbar
        // and the pane mini-toolbars (PaneFilterBar / MiniToolbar) for a consistent
        // glass look across the sidebar chrome (#2550).
        //
        // The icon row is wrapped in ViewThatFits (#3059): the full row shows when
        // it fits; on a narrow sidebar it falls back to a few inline icons + an
        // '…' overflow menu instead of cramming/clipping all 8 icons.
        GlassEffectContainer {
            ViewThatFits(in: .horizontal) {
                fullModeRow
                compactModeRow
            }
            .padding(.horizontal, 8)
            .frame(maxWidth: .infinity, maxHeight: MiniToolbar<EmptyView, EmptyView>.standardHeight)  // Normalize to 44pt
            .glassEffect(.regular, in: RoundedRectangle(cornerRadius: 8))
        }
    }

    // MARK: - Rows

    /// Preferred candidate — every enabled mode icon inline, unchanged (#3059):
    /// separators, badges, and feature gating exactly as before.
    private var fullModeRow: some View {
        HStack(spacing: 2) {
            // Content modes (1-4)
            Group {
                modeIcon(.library)

                if featureManager.isSearchEnabled {
                    modeIcon(.search)
                }

                if featureManager.isChatEnabled {
                    modeIcon(.chat)
                }

                if featureManager.isWorkflowsEnabled {
                    modeIcon(.workflows)
                }

                if featureManager.isResearchEnabled {
                    modeIcon(.research)
                }

                if featureManager.isKnowledgeGraphEnabled {
                    modeIcon(.knowledgeGraph)
                }
            }

            if featureManager.isAutomationEnabled {
                modeSeparator
                modeIcon(.automation)
            }

        }
    }

    /// Narrow-sidebar fallback (#3059): the inline partition of enabled modes
    /// (selected + `.library` always kept) + an '…' menu for the remainder.
    private var compactModeRow: some View {
        let split = Self.partition(
            modes: enabledModes,
            selected: selectedMode,
            limit: compactInlineLimit
        )
        return HStack(spacing: 2) {
            ForEach(split.inline, id: \.self) { mode in
                modeIcon(mode)
            }
            if !split.overflow.isEmpty {
                overflowModeMenu(split.overflow)
            }
        }
    }

    // MARK: - Helper Views

    /// One mode icon — the single definition both rows use (badge + selection +
    /// tap all identical to the original per-mode call sites).
    @ViewBuilder
    private func modeIcon(_ mode: SidebarMode) -> some View {
        SidebarModeIcon(
            mode: mode,
            isSelected: selectedMode == mode,
            badgeCount: badgeCount(for: mode)
        ) {
            selectMode(mode)
        }
    }

    /// Trailing '…' menu listing the overflowed modes as labelled buttons that
    /// call the same `selectMode(_:)` (#3059).
    private func overflowModeMenu(_ modes: [SidebarMode]) -> some View {
        Menu {
            ForEach(modes, id: \.self) { mode in
                Button {
                    selectMode(mode)
                } label: {
                    Label(mode.label, systemImage: mode.icon)
                }
            }
        } label: {
            Image(systemName: "ellipsis.circle")
                .frame(
                    minWidth: MiniToolbar<EmptyView, EmptyView>.touchTargetSide,
                    minHeight: MiniToolbar<EmptyView, EmptyView>.touchTargetSide
                )
        }
        .menuIndicator(.hidden)
        .fixedSize()
        .help("More modes")
        .accessibilityLabel("More sidebar modes")
    }

    private var modeSeparator: some View {
        Divider()
            .frame(height: 16)
            .padding(.horizontal, 4)
    }

    // MARK: - Enabled modes + partition

    /// The enabled modes in display order, gated by the feature manager — the
    /// same set + order the full row renders.
    private var enabledModes: [SidebarMode] {
        var modes: [SidebarMode] = [.library]
        if featureManager.isSearchEnabled { modes.append(.search) }
        if featureManager.isChatEnabled { modes.append(.chat) }
        if featureManager.isWorkflowsEnabled { modes.append(.workflows) }
        if featureManager.isResearchEnabled { modes.append(.research) }
        if featureManager.isKnowledgeGraphEnabled { modes.append(.knowledgeGraph) }
        if featureManager.isAutomationEnabled { modes.append(.automation) }
        return modes
    }

    /// Pure inline/overflow split for the narrow-sidebar fallback (#3059). The
    /// selected mode and `.library` are ALWAYS inline (never lose context or the
    /// home affordance); the rest fill inline in order up to `limit`, and any
    /// remainder overflows. Order is preserved. Unit-tested.
    static func partition(
        modes: [SidebarMode],
        selected: SidebarMode,
        limit: Int
    ) -> (inline: [SidebarMode], overflow: [SidebarMode]) {
        guard limit > 0, modes.count > limit else { return (modes, []) }
        var inline: [SidebarMode] = []
        var overflow: [SidebarMode] = []
        for mode in modes {
            let mustPin = (mode == .library || mode == selected)
            if mustPin || inline.count < limit {
                inline.append(mode)
            } else {
                overflow.append(mode)
            }
        }
        return (inline, overflow)
    }

    // MARK: - Badge Counts

    private func badgeCount(for mode: SidebarMode) -> Int {
        switch mode {
        default:
            return 0
        }
    }

    // MARK: - Actions

    private func selectMode(_ mode: SidebarMode) {
        logger.debug("Mode selected: \(mode.label)")
        selectedMode = mode
    }
}

#Preview {
    VStack {
        SidebarModeBar(selectedMode: .constant(.library))
        Divider()
        Text("Sidebar content would go here")
            .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    .frame(width: 280, height: 400)
    .environment(WorkflowExecutionObserver())
    .environment(FeatureManager.shared)
}
