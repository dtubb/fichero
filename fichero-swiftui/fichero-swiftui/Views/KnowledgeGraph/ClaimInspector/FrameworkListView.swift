import SwiftUI
import FicheroAPIClient

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
            frameworkGrid
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
            Image(systemName: "square.grid.2x2")
                .font(.system(size: 36))
                .foregroundColor(.secondary)
            Text("No Frameworks")
                .font(.headline)
            Text("Create interpretive frameworks to analyze claims")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    private var frameworkGrid: some View {
        ScrollView {
            LazyVStack(spacing: 8) {
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
