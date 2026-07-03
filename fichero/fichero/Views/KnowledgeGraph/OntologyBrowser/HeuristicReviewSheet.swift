import FicheroAPIClient
import SwiftUI

// MARK: - Heuristic Predictions Review

/// Identifiable wrapper so SwiftUI can drive the .sheet(item:) modifier
/// from an optional struct that isn't itself Identifiable.
struct IdentifiedPredictions: Identifiable {
    let id = UUID()
    let response: Components.Schemas.HeuristicPredictionsResponse
}

struct IdentifiedEntity: Identifiable {
    let id = UUID()
    let entity: Components.Schemas.KnowledgeEntity
}

/// Sheet that presents heuristic-prediction candidates with accept/
/// reject actions. Accept calls POST /api/claims/{id}/links to write
/// a KnowledgeClaimLink with relation_type=related_to and link_quality
/// = the similarity score. Reject just dismisses the row — there's no
/// negative-example storage yet, that's a future curation surface.
struct HeuristicReviewSheet: View {
    let response: Components.Schemas.HeuristicPredictionsResponse
    let dismiss: () -> Void

    @State private var processed: Set<String> = []
    @State private var accepted: Set<String> = []
    @State private var status: String = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header
            Divider()
            list
            Divider()
            footer
        }
        // Mac-only fixed size; iPhone/iPad sheets size to the screen (#2802).
        #if os(macOS)
        .frame(width: 580, height: 480)
        #endif
    }

    private var header: some View {
        HStack {
            VStack(alignment: .leading, spacing: 2) {
                Text("Suggested Links")
                    .font(.headline)
                Text("\(response.predictions.count) candidates from embedding similarity (#919 5c)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            Spacer()
            Button("Done", action: dismiss)
                .keyboardShortcut(.cancelAction)
        }
        .padding()
    }

    private var list: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 8) {
                ForEach(Array(response.predictions.enumerated()), id: \.offset) { _, pred in
                    predictionRow(pred)
                }
            }
            .padding()
        }
    }

    private func predictionRow(_ pred: Components.Schemas.HeuristicPredictionItem) -> some View {
        let key = "\(pred.sourceClaimId)→\(pred.targetClaimId)"
        let done = processed.contains(key)
        return HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text("Similarity \(String(format: "%.2f", pred.similarityScore))")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                Text(pred.sourceClaimId)
                    .font(.caption2)
                    .monospaced()
                    .lineLimit(1)
                    .foregroundStyle(.secondary)
                Image(systemName: "arrow.down.right")
                    .foregroundStyle(.secondary)
                Text(pred.targetClaimId)
                    .font(.caption2)
                    .monospaced()
                    .lineLimit(1)
                    .foregroundStyle(.secondary)
            }
            Spacer(minLength: 0)
            if done {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundStyle(.green)
            } else {
                Button("Accept") { Task { await accept(pred, key: key) } }
                    .buttonStyle(.borderedProminent)
                    .controlSize(.small)
                Button("Reject") {
                    accepted.remove(key)
                    processed.insert(key)
                    status = "Rejected \(pred.sourceClaimId) ↔ \(pred.targetClaimId)"
                }
                    .buttonStyle(.bordered)
                    .controlSize(.small)
            }
        }
        .padding(8)
        .background(Color(.windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .opacity(done ? 0.6 : 1)
    }

    private var footer: some View {
        HStack {
            Text(status)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Text(
                "\(Self.reviewedCount(total: response.predictions.count, processed: processed))/\(response.predictions.count) reviewed · "
                + "\(Int(Self.acceptanceRate(processed: processed, accepted: accepted) * 100))% accepted"
            )
            .font(.caption2)
            .foregroundStyle(.secondary)
        }
        .padding(.horizontal)
        .padding(.vertical, 6)
    }

    private func accept(_ pred: Components.Schemas.HeuristicPredictionItem, key: String) async {
        guard let library = LibraryManager.shared.globalLibrary else { return }
        do {
            _ = try await library.entityService.createClaimLink(
                claimId: pred.sourceClaimId,
                relatedClaimId: pred.targetClaimId,
                relationType: .supports,
                linkQuality: pred.similarityScore,
                evidence: "Heuristic similarity \(String(format: "%.3f", pred.similarityScore))"
            )
            accepted.insert(key)
            processed.insert(key)
            status = "Linked \(pred.sourceClaimId) ↔ \(pred.targetClaimId)"
        } catch {
            status = "Failed: \(error.localizedDescription)"
        }
    }

    static func reviewedCount(total: Int, processed: Set<String>) -> Int {
        min(total, processed.count)
    }

    static func acceptanceRate(processed: Set<String>, accepted: Set<String>) -> Double {
        guard !processed.isEmpty else { return 0 }
        let acceptedCount = accepted.intersection(processed).count
        return Double(acceptedCount) / Double(processed.count)
    }
}
