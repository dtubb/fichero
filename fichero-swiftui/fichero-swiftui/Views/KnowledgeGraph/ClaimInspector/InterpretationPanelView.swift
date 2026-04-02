import SwiftUI
import FicheroAPIClient

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

// MARK: - Interpretation List View

/// Shows all interpretations with filtering by framework
struct InterpretationListView: View {
    @State private var interpretations: [Components.Schemas.Interpretation] = []
    @State private var frameworks: [Components.Schemas.InterpretiveFramework] = []
    @State private var selectedFrameworkId: String?
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        VStack(spacing: 0) {
            frameworkPicker

            Divider()

            if isLoading {
                loadingState
            } else if let errorMessage {
                errorState(errorMessage)
            } else if interpretations.isEmpty {
                emptyState
            } else {
                interpretationList
            }
        }
        .task {
            await loadData()
        }
    }

    private var frameworkPicker: some View {
        HStack {
            Picker("Framework", selection: $selectedFrameworkId) {
                Text("All Frameworks").tag(String?.none)
                ForEach(frameworks, id: \.id) { framework in
                    Text(framework.name).tag(String?.some(framework.id ?? ""))
                }
            }
            .pickerStyle(.menu)
        }
        .padding(.horizontal, 8)
        .padding(.vertical, 6)
    }

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading interpretations...")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 28))
                .foregroundStyle(.orange)
            Text("Failed to Load")
                .font(.subheadline)
                .fontWeight(.medium)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "text.bubble")
                .font(.system(size: 36))
                .foregroundColor(.secondary)
            Text("No Interpretations")
                .font(.headline)
            Text("Apply a framework to create interpretations")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private var interpretationList: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(interpretations, id: \.id) { interpretation in
                    InterpretationCard(interpretation: interpretation)
                }
            }
            .padding()
        }
    }

    private func loadData() async {
        isLoading = true
        errorMessage = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = HermeneuticsServiceGenerated(apiClient: library!.apiClient)

            async let frameworksLoad = service.listFrameworks()
            async let interpretationsLoad = service.listInterpretations(frameworkId: selectedFrameworkId)

            frameworks = try await frameworksLoad
            interpretations = try await interpretationsLoad
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }
}

// MARK: - Interpretation Card

struct InterpretationCard: View {
    let interpretation: Components.Schemas.Interpretation

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                if let act = interpretation.act {
                    InterpretiveActBadge(act: act)
                }
                Spacer()
                if let confidence = interpretation.confidence {
                    Text(String(format: "%.0f%%", confidence * 100))
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            Text(interpretation.interpretationText)
                .font(.body)
                .lineLimit(4)
                .textSelection(.enabled)

            if let insights = interpretation.keyInsights, !insights.isEmpty {
                VStack(alignment: .leading, spacing: 4) {
                    Text("Key Insights")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    ForEach(insights, id: \.self) { insight in
                        Text("• \(insight)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(12)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Interpretive Act Badge

struct InterpretiveActBadge: View {
    let act: Components.Schemas.InterpretiveActType

    var body: some View {
        Text(act.rawValue.capitalized)
            .font(.caption)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(backgroundColor)
            .foregroundStyle(foregroundColor)
            .clipShape(RoundedRectangle(cornerRadius: 4))
    }

    private var backgroundColor: Color {
        switch act {
        case .describe: return .blue.opacity(0.2)
        case .interpret: return .purple.opacity(0.2)
        case .evaluate: return .orange.opacity(0.2)
        case .situate: return .green.opacity(0.2)
        }
    }

    private var foregroundColor: Color {
        switch act {
        case .describe: return .blue
        case .interpret: return .purple
        case .evaluate: return .orange
        case .situate: return .green
        }
    }
}

// MARK: - Framework List View

struct FrameworkListView: View {
    @State private var frameworks: [Components.Schemas.InterpretiveFramework] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        if isLoading {
            loadingState
        } else if let errorMessage {
            errorState(errorMessage)
        } else if frameworks.isEmpty {
            emptyState
        } else {
            frameworkList
        }
        .task {
            await loadFrameworks()
        }
    }

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading frameworks...")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 28))
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "square.grid.2x2")
                .font(.system(size: 36))
                .foregroundColor(.secondary)
            Text("No Frameworks")
                .font(.headline)
            Text("Create a framework to start interpreting sources")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private var frameworkList: some View {
        ScrollView {
            LazyVStack(spacing: 12) {
                ForEach(frameworks, id: \.id) { framework in
                    FrameworkCard(framework: framework)
                }
            }
            .padding()
        }
    }

    private func loadFrameworks() async {
        isLoading = true
        do {
            let library = LibraryManager.shared.globalLibrary
            let service = HermeneuticsServiceGenerated(apiClient: library!.apiClient)
            frameworks = try await service.listFrameworks()
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

// MARK: - Framework Card

struct FrameworkCard: View {
    let framework: Components.Schemas.InterpretiveFramework

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text(framework.name)
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                if let frameworkType = framework.frameworkType {
                    Text(frameworkType.rawValue.capitalized)
                        .font(.caption2)
                        .padding(.horizontal, 6)
                        .padding(.vertical, 2)
                        .background(Color.accentColor.opacity(0.15))
                        .foregroundStyle(.accentColor)
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                }
            }

            if let description = framework.description_p, !description.isEmpty {
                Text(description)
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
            }

            if let coreQuestions = framework.coreQuestions, !coreQuestions.isEmpty {
                VStack(alignment: .leading, spacing: 2) {
                    Text("Core Questions")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                    ForEach(coreQuestions.prefix(2), id: \.self) { question in
                        Text("• \(question)")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
            }
        }
        .padding(12)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}

// MARK: - Hermeneutic Circle View

struct HermeneuticCircleView: View {
    @State private var states: [Components.Schemas.HermeneuticCircleState] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        if isLoading {
            loadingState
        } else if let errorMessage {
            errorState(errorMessage)
        } else if states.isEmpty {
            emptyState
        } else {
            circleNavigation
        }
        .task {
            await loadStates()
        }
    }

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading circle...")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 28))
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "arrow.triangle.circlepath")
                .font(.system(size: 36))
                .foregroundColor(.secondary)
            Text("No Active Circle")
                .font(.headline)
            Text("Navigate between interpretations using the hermeneutic circle")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private var circleNavigation: some View {
        ScrollView {
            VStack(spacing: 12) {
                ForEach(states, id: \.id) { state in
                    CircleStateCard(state: state)
                }
            }
            .padding()
        }
    }

    private func loadStates() async {
        isLoading = true
        do {
            let library = LibraryManager.shared.globalLibrary
            let service = HermeneuticsServiceGenerated(apiClient: library!.apiClient)
            states = try await service.listCircleStates()
        } catch {
            errorMessage = error.localizedDescription
        }
        isLoading = false
    }
}

// MARK: - Circle State Card

struct CircleStateCard: View {
    let state: Components.Schemas.HermeneuticCircleState

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Circle State")
                    .font(.subheadline)
                    .fontWeight(.semibold)
                Spacer()
                if let position = state.position {
                    Text("Step \(position)")
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            if let currentClaimId = state.currentClaimId {
                LabeledContent("Current Claim") {
                    Text(currentClaimId)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }

            if let currentInterpretationId = state.currentInterpretationId {
                LabeledContent("Interpretation") {
                    Text(currentInterpretationId)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }
        }
        .padding(12)
        .background(Color(.controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 8))
    }
}
