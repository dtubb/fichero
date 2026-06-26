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
                .frame(minWidth: 980, minHeight: 640)
                .padding(16)
        }
        .sheet(isPresented: $showClaimReviewQueueSheet) {
            ClaimReviewQueueSheet(entity: entity, claims: filteredClaims)
                .frame(minWidth: 920, minHeight: 620)
                .padding(16)
        }
    }

    var claimsCountLabel: String {
        let total = claims.count
        let shown = filteredClaims.count
        return shown == total ? "\(total)" : "\(shown) / \(total)"
    }
}
