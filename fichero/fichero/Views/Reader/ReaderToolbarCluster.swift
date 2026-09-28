import SwiftUI

/// One cluster of the Reader's toolbar that collapses to a menu when there is no room.
struct ReaderToolbarCluster<Expanded: View>: View {
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
        // EXPLICIT if/else, never an optional FIRST ViewThatFits candidate
        // (views audit §4, PLAUSIBLE→confirmed by the API contract): when
        // collapsed, the old `if isExpanded { … }` candidate was an empty
        // ConditionalContent of ZERO size — which always fits — so
        // ViewThatFits chose it, the cluster rendered NOTHING, and the
        // collapsed button below it was unreachable: no way to re-expand.
        if isExpanded {
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 4) {
                    toggleButton(help: "Collapse")
                    expandedContent
                }
                // Fallback when the expanded row doesn't fit the pane.
                toggleButton(help: collapsedHelp)
            }
        } else {
            toggleButton(help: collapsedHelp)
        }
    }

    private func toggleButton(help: String) -> some View {
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
        .help(help)
        .accessibilityLabel(help)
    }
}
