import SwiftUI
import FicheroAPIClient

/// Links tab showing claim-to-claim relationships (supports/contradicts/refines)
struct ClaimInspectorLinksTab: View {
    let claim: Components.Schemas.KnowledgeClaim

    @State private var links: [Components.Schemas.KnowledgeClaimLink] = []
    @State private var isLoading = false
    @State private var errorMessage: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                if isLoading {
                    loadingState
                } else if let errorMessage {
                    errorState(errorMessage)
                } else if links.isEmpty {
                    emptyLinksState
                } else {
                    linksList
                }
            }
            .padding()
        }
        .task {
            await loadLinks()
        }
    }

    // MARK: - Data Loading

    private func loadLinks() async {
        guard let claimId = claim.id else { return }
        isLoading = true
        errorMessage = nil

        do {
            let library = LibraryManager.shared.globalLibrary
            let service = KnowledgeGraphServiceGenerated(apiClient: library!.apiClient)
            links = try await service.listClaimLinks(claimId: claimId)
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    // MARK: - States

    private var loadingState: some View {
        VStack(spacing: 12) {
            ProgressView()
            Text("Loading links...")
                .font(.caption)
                .foregroundStyle(.secondary)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }

    private func errorState(_ message: String) -> some View {
        VStack(spacing: 12) {
            Image(systemName: "exclamationmark.triangle")
                .font(.system(size: 28))
                .foregroundStyle(.orange)

            Text("Failed to Load Links")
                .font(.subheadline)
                .fontWeight(.medium)

            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)

            Button("Retry") {
                Task { await loadLinks() }
            }
            .buttonStyle(.bordered)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }

    private var emptyLinksState: some View {
        VStack(spacing: 12) {
            Image(systemName: "link")
                .font(.system(size: 28))
                .foregroundColor(.secondary)

            Text("No Links")
                .font(.subheadline)
                .fontWeight(.medium)

            Text("This claim has no linked claims")
                .font(.caption)
                .foregroundColor(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 24)
    }

    private var linksList: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Related Claims")
                .font(.subheadline)
                .fontWeight(.semibold)

            ForEach(links, id: \.id) { link in
                ClaimLinkCard(link: link, currentClaimId: claim.id)
            }
        }
    }
}

// MARK: - Claim Link Card

struct ClaimLinkCard: View {
    let link: Components.Schemas.KnowledgeClaimLink
    let currentClaimId: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                LinkTypeBadge(type: link.linkType)
                Spacer()
                if let direction = link.direction {
                    Text(direction)
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
            }

            if let sourceClaimId = link.sourceClaimId {
                LabeledContent("From") {
                    Text(sourceClaimId)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                }
            }

            if let targetClaimId = link.targetClaimId {
                LabeledContent("To") {
                    Text(targetClaimId)
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

// MARK: - Link Type Badge

struct LinkTypeBadge: View {
    let type: String

    var body: some View {
        Text(type.capitalized)
            .font(.caption)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(backgroundColor)
            .foregroundStyle(foregroundColor)
            .clipShape(RoundedRectangle(cornerRadius: 4))
    }

    private var backgroundColor: Color {
        switch type.lowercased() {
        case "supports": return .blue.opacity(0.2)
        case "contradicts": return .red.opacity(0.2)
        case "refines": return .purple.opacity(0.2)
        case "supersedes": return .orange.opacity(0.2)
        default: return .gray.opacity(0.2)
        }
    }

    private var foregroundColor: Color {
        switch type.lowercased() {
        case "supports": return .blue
        case "contradicts": return .red
        case "refines": return .purple
        case "supersedes": return .orange
        default: return .gray
        }
    }
}
