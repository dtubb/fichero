import FicheroAPIClient
import SwiftUI

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
