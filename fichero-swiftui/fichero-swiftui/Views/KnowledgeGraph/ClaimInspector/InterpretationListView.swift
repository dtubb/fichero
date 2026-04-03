import FicheroAPIClient
import SwiftUI

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
            LazyVStack(spacing: 8) {
                ForEach(filteredInterpretations, id: \.id) { interpretation in
                    InterpretationCard(interpretation: interpretation)
                }
            }
            .padding()
        }
    }

    private var filteredInterpretations: [Components.Schemas.Interpretation] {
        if let selectedFrameworkId, !selectedFrameworkId.isEmpty {
            return interpretations.filter { $0.frameworkId == selectedFrameworkId }
        }
        return interpretations
    }

    private func loadData() async {
        isLoading = true
        do {
            let library = LibraryManager.shared.globalLibrary
            let service = HermeneuticsServiceGenerated(apiClient: library!.apiClient)
            async let interpretationsLoad = service.listInterpretations()
            async let frameworksLoad = service.listFrameworks()
            let (interpretationsResult, frameworksResult) = try await (interpretationsLoad, frameworksLoad)
            interpretations = interpretationsResult
            frameworks = frameworksResult
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
