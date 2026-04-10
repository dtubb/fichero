import SwiftUI

/// Tab selection for InterpretationPanel
enum InterpretationPanelTab: String, CaseIterable, Identifiable {
    case interpretations = "Interpretations"
    case frameworks = "Frameworks"
    case circle = "Circle"

    var id: String { rawValue }

    var icon: String {
        switch self {
        case .interpretations: return "text.bubble"
        case .frameworks: return "square.grid.2x2"
        case .circle: return "arrow.triangle.circlepath"
        }
    }
}

/// Panel for hermeneutics: interpretations, frameworks, and hermeneutic circle navigation
struct InterpretationPanel: View {
    @State private var selectedTab: InterpretationPanelTab = .interpretations

    var body: some View {
        VStack(spacing: 0) {
            tabBar

            Divider()

            switch selectedTab {
            case .interpretations:
                InterpretationListView()
            case .frameworks:
                FrameworkListView()
            case .circle:
                HermeneuticCircleView()
            }
        }
        .frame(minWidth: 300, maxWidth: .infinity)
    }

    private var tabBar: some View {
        HStack(spacing: 2) {
            ForEach(InterpretationPanelTab.allCases) { tab in
                Button {
                    selectedTab = tab
                } label: {
                    Image(systemName: tab.icon)
                        .font(Font.system(size: 13, weight: .regular))
                        .frame(maxWidth: .infinity)
                        .padding(.vertical, 6)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .background(
                    RoundedRectangle(cornerRadius: 6)
                        .fill(selectedTab == tab
                                ? Color.accentColor.opacity(0.15)
                                : Color.clear)
                )
                .foregroundStyle(selectedTab == tab ? Color.accentColor : Color.secondary)
                .help(tab.rawValue)
            }
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }
}
