import FicheroAPIClient
import SwiftUI

// MARK: - Claims

extension EntityDetailView {
    var claimsSection: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("Claims")
                    .font(.subheadline)
                    .fontWeight(.semibold)

                Spacer()

                // Source-groups mode: switch to per-source-document
                // grouped prose view backed by the entity inspector
                // endpoint. (#1183)
                Button {
                    sourceGroupsMode = true
                } label: {
                    Image(systemName: "doc.text.magnifyingglass")
                        .font(.caption)
                        .foregroundStyle(Color.secondary)
                }
                .buttonStyle(.plain)
                .help("View claims grouped by source document")

                if isLoadingClaims {
                    ProgressView()
                        .scaleEffect(0.7)
                } else {
                    Button {
                        showClaimReviewQueueSheet = true
                    } label: {
                        Label("Queue", systemImage: "checklist")
                            .font(.caption2)
                    }
                    .buttonStyle(.bordered)
                    .disabled(filteredClaims.isEmpty)
                    .help("Review queue with batch curation transitions")

                    Button {
                        showContradictionTriageSheet = true
                    } label: {
                        Label("Triage", systemImage: "arrow.left.and.right.square")
                            .font(.caption2)
                    }
                    .buttonStyle(.bordered)
                    .disabled(filteredClaims.isEmpty)
                    .help("Review contradictions side-by-side")

                    Button(role: .destructive) {
                        promptDeleteSelectedClaims()
                    } label: {
                        Label("Delete", systemImage: "trash")
                            .font(.caption2)
                    }
                    .buttonStyle(.bordered)
                    .disabled(selectedClaimIds.isEmpty)
                    .help("Delete selected claims")

                    Text(claimsCountLabel)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }
            }

            // Twin filter strips — epistemic (how firmly asserted) +
            // ontological / claim_type (what kind of knowledge). Both
            // axes shipped in #892. @AppStorage persists across views.
            if !claims.isEmpty {
                filterStrips
            }

            if isLoadingClaims {
                HStack {
                    Spacer()
                    ProgressView()
                    Spacer()
                }
                .padding(.vertical, 20)
            } else if claims.isEmpty {
                Text("No claims reference this entity")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 12)
            } else if filteredClaims.isEmpty {
                Text("All \(claims.count) claims filtered out — toggle chips above to reveal")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                    .padding(.vertical, 12)
            } else {
                // Native SwiftUI List for the source-annotation SVO triples
                // — free macOS selection emphasis + scrolling. Bounded height
                // so it nests cleanly inside the detail ScrollView. Cap at 10
                // visible by default; "show all" reveals the rest. (#1864 /
                // #994 / #989 follow-up)
                let cap = 10
                let visibleClaims = showAllClaims
                    ? Array(filteredClaims)
                    : Array(filteredClaims.prefix(cap))
                List(selection: $selectedClaimIds) {
                    ForEach(visibleClaims, id: \.id) { claim in
                        ClaimSummaryCard(
                            claim: claim,
                            focusedEntityId: entity.id,
                            onNavigateToSource: onNavigateToSource
                        )
                        .tag(claim.id ?? "")
                        .listRowInsets(EdgeInsets(top: 4, leading: 0, bottom: 4, trailing: 0))
                        .listRowSeparator(.hidden)
                        .listRowBackground(Color.clear)
                    }
                }
                .listStyle(.plain)
                .scrollContentBackground(.hidden)
                .frame(minHeight: 80, maxHeight: 520)
                #if os(macOS)
                .onDeleteCommand(perform: promptDeleteSelectedClaims)
                #endif
                if filteredClaims.count > cap {
                    Button {
                        showAllClaims.toggle()
                    } label: {
                        Text(showAllClaims
                                ? "Show \(cap) of \(filteredClaims.count)"
                                : "Show all \(filteredClaims.count) claims")
                            .font(.caption)
                            .foregroundColor(.accentColor)
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 4)
                }
            }
        }
        .padding()
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(.regularMaterial)
        .clipShape(RoundedRectangle(cornerRadius: 8))
        .sheet(isPresented: $showContradictionTriageSheet) {
            ContradictionTriageSheet(entity: entity, claims: filteredClaims)
                // Fixed sizing is a Mac window affordance; on iPhone/iPad the
                // sheet must size to the screen or it clips (#2802).
                #if os(macOS)
                .frame(minWidth: 980, minHeight: 640)
                #endif
                .padding(16)
        }
        .sheet(isPresented: $showClaimReviewQueueSheet) {
            ClaimReviewQueueSheet(entity: entity, claims: filteredClaims)
                #if os(macOS)
                .frame(minWidth: 920, minHeight: 620)
                #endif
                .padding(16)
        }
        .alert("Delete Claims?", isPresented: $showingDeleteClaimsConfirmation) {
            Button("Cancel", role: .cancel) {
                claimsToDelete = []
            }
            Button("Delete", role: .destructive) {
                let claims = claimsToDelete
                if !claims.isEmpty {
                    Task { await deleteSelectedClaims(claims) }
                }
            }
        } message: {
            if claimsToDelete.count == 1, let claim = claimsToDelete.first {
                Text("This removes the claim \"\(provenanceSummary(for: claim))\" from the knowledge graph.")
            } else if !claimsToDelete.isEmpty {
                Text("This removes \(claimsToDelete.count) claims from the knowledge graph.")
            }
        }
    }

    var claimsCountLabel: String {
        let total = claims.count
        let shown = filteredClaims.count
        return shown == total ? "\(total)" : "\(shown) / \(total)"
    }

    private var selectedClaimsForDeletion: [Components.Schemas.KnowledgeClaim] {
        let selectedIds = selectedClaimIds
        guard !selectedIds.isEmpty else { return [] }
        return filteredClaims.filter { claim in
            guard let id = claim.id else { return false }
            return selectedIds.contains(id)
        }
    }

    private func promptDeleteSelectedClaims() {
        let claims = selectedClaimsForDeletion
        guard !claims.isEmpty else { return }
        claimsToDelete = claims
        showingDeleteClaimsConfirmation = true
    }

    /// Short human label for a claim in confirmation copy — SVO triple when
    /// available, else the claim text. Mirrors EntityDigestView.provenanceSummary.
    private func provenanceSummary(for claim: Components.Schemas.KnowledgeClaim) -> String {
        if let svo = ClaimSummaryCard.svoTriple(for: claim) {
            return [svo.subject, svo.verb, svo.object]
                .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
                .filter { !$0.isEmpty }
                .joined(separator: " · ")
        }
        let fallback = claim.text.trimmingCharacters(in: .whitespacesAndNewlines)
        return fallback.isEmpty ? "Untitled claim" : fallback
    }

    private func deleteSelectedClaims(_ claims: [Components.Schemas.KnowledgeClaim]) async {
        let claimIds = claims.compactMap(\.id)
        guard !claimIds.isEmpty else { return }
        do {
            try await claimStore.delete(claimIds: claimIds)
            selectedClaimIds.subtract(claimIds)
            claimsToDelete = []
            showingDeleteClaimsConfirmation = false
        } catch {
            // Leave the selection in place so the user can retry or inspect.
        }
    }
}
