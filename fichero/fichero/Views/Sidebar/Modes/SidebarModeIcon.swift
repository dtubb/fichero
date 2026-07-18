import SwiftUI

/// Individual mode icon with optional badge count
/// Used in the SidebarModeBar for Xcode-style mode switching
struct SidebarModeIcon: View {
    let mode: SidebarMode
    let isSelected: Bool
    let badgeCount: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            ZStack(alignment: .topTrailing) {
                Image(systemName: isSelected ? selectedIcon : mode.icon)
                    .font(.system(size: 12, weight: isSelected ? .semibold : .regular))
                    .foregroundStyle(isSelected ? Color.accentColor : Color.secondary)
                    .frame(width: 26, height: 24)
                    .background(
                        RoundedRectangle(cornerRadius: 5)
                            .fill(isSelected ? Color.accentColor.opacity(0.12) : Color.clear)
                    )
                    .contentShape(Rectangle())

                // Badge for counts > 0
                if badgeCount > 0 {
                    badgeView
                }
            }
        }
        .buttonStyle(.plain)
        .focusEffectDisabled()
        .help(mode.helpText)
        .accessibilityLabel(mode.label)
        .accessibilityIdentifier("sidebarMode.\(mode.rawValue)")
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityHint(isSelected ? "Currently active" : "Switch to \(mode.label)")
    }

    /// Selected state uses filled variant where available
    private var selectedIcon: String {
        switch mode {
        case .library:
            return "folder.fill"
        case .search:
            return "magnifyingglass"
        case .chat:
            return "bubble.left.and.bubble.right.fill"
        case .workflows:
            return "bolt.fill"
        case .automation:
            return "gearshape.2.fill"
        case .activity:
            return "clock.fill"
        case .research:
            return "flask.fill"
        case .knowledgeGraph:
            return "point.3.connected.trianglepath.dotted"
        }
    }

    @ViewBuilder
    private var badgeView: some View {
        Text(badgeCount > 99 ? "99+" : "\(badgeCount)")
            .font(.system(size: 9, weight: .bold))
            .foregroundStyle(.white)
            .padding(.horizontal, 4)
            .padding(.vertical, 1)
            .background(badgeColor, in: Capsule())
            .offset(x: 6, y: -4)
    }

    private var badgeColor: Color {
        switch mode {
        case .activity:
            return .blue  // Blue for running items
        default:
            return .secondary
        }
    }
}

#Preview("Selected") {
    HStack {
        SidebarModeIcon(mode: .library, isSelected: true, badgeCount: 0) {}
        SidebarModeIcon(mode: .activity, isSelected: true, badgeCount: 3) {}
    }
    .padding()
}

#Preview("All Modes") {
    HStack(spacing: 4) {
        ForEach(SidebarMode.allCases, id: \.self) { mode in
            SidebarModeIcon(
                mode: mode,
                isSelected: mode == .library,
                badgeCount: mode == .activity ? 2 : 0
            ) {}
        }
    }
    .padding()
}
