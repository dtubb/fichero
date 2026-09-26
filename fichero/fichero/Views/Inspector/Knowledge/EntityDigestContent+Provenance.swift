import FicheroAPIClient
import SwiftUI

// Split out of EntityDigestView.swift (#4896 lint follow-up: type_body_length
// 365/250, file_length 784/400) — a MOVE only, no behaviour change. See the
// doc comment on `EntityDigestContent` in EntityDigestView.swift for the
// access-level rule this split follows.
//
// This is the #4888 target: `provenanceSection`'s bespoke grouped List
// (`.frame(minHeight: 160, maxHeight: 520)` below) is the claims list finding
// B5 will replace with the shared claims table — isolated here on purpose so
// that change stays a one-file diff instead of reopening this whole type.
extension EntityDigestContent {
    var provenanceSection: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Source Annotations")
                .font(.headline)
                .padding(.bottom, 4)

            let state = Self.statementsState(isLoading: isLoading, isEmpty: claims.isEmpty)
            if state == .loading {
                ProgressView()
            } else if state == .empty {
                Text("No statements about \(entity.canonicalName) yet.")
                    .foregroundStyle(.secondary)
            } else {
                let grouped = Dictionary(grouping: claims, by: { $0.sourceDocumentId ?? "" })
                let sortedDocIds = grouped.keys.sorted()

                // Single-selection List with STABLE, non-optional tags. The old
                // `.tag(claim.id)` was `String?` while the selection was
                // `Set<String>` — the type mismatch collapsed identity so
                // clicking one row highlighted them all. A `String?` selection
                // matched by non-optional `String` tags fixes it, and
                // `inspectorListRowTarget()` makes the whole row the hit target.
                List(selection: $selectedClaimRowId) {
                    ForEach(sortedDocIds, id: \.self) { docId in
                        Section(header: Label(docName(for: docId), systemImage: "doc.text")) {
                            ForEach(Array((grouped[docId] ?? []).enumerated()), id: \.offset) { index, claim in
                                provenanceRow(claim)
                                    .inspectorListRowTarget()
                                    .tag(claim.id ?? "\(docId)#\(index)")
                                    .listRowSeparator(.hidden)
                            }
                        }
                    }
                }
                .listStyle(.inset)
                .scrollContentBackground(.hidden)
                .frame(minHeight: 160, maxHeight: 520)
                // Selecting a claim reveals its source (#4393 part 2), through
                // the SAME cursor the outline, annotations and artifacts use —
                // mirroring `SourceOutlineView`'s shape exactly. A claim with
                // no recorded span still navigates to its page; it just does
                // not draw a highlight, because a confidently wrong one over a
                // manuscript is worse than none.
                .onChange(of: selectedClaimRowId) { _, newSelection in
                    guard let newSelection,
                          let claim = claims.first(where: { $0.id == newSelection }),
                          // #4834: this list mirrors SourceOutlineView's
                          // shape (its own comment above) — a provenance ROW
                          // selection, not the biography sentence named as
                          // priority-2; `.reader` stated explicitly.
                          let request = ClaimSourceRequest.request(for: claim, destination: .reader) else { return }
                    claimSourceNavigationState?.request(request)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
    }

    private func provenanceRow(_ claim: Components.Schemas.KnowledgeClaim) -> some View {
        let summary = provenanceSummary(for: claim)
        let badge = provenanceBadgeLabel(for: claim)

        return HStack(alignment: .firstTextBaseline, spacing: 10) {
            Text(summary)
                .font(.body)
                .textSelection(.enabled)
                .lineLimit(2)

            Spacer(minLength: 8)

            Text(badge)
                .font(.caption)
                .foregroundStyle(.secondary)
                .lineLimit(1)
        }
        .padding(.vertical, 2)
    }

    /// The entity this digest is showing, which every claim below is grouped
    /// under — so its name is redundant on each row (#4393).
    private var groupSubject: String? { entity.canonicalName }

    private func provenanceSummary(for claim: Components.Schemas.KnowledgeClaim) -> String {
        ClaimLine.statement(for: claim, groupSubject: groupSubject)
    }

    private func provenanceBadgeLabel(for claim: Components.Schemas.KnowledgeClaim) -> String {
        let metadata = claim.metadata?.additionalProperties.value ?? [:]
        let raw = (
            claim.confidenceSource
            ?? metadata["confidence_source"] as? String
            ?? metadata["confidenceSource"] as? String
        )?.trimmingCharacters(in: .whitespacesAndNewlines).lowercased()

        switch raw {
        case "human_review", "human", "manual", "user", "curator", "editor", "researcher":
            return "Human"
        case "llm_logprob", "llm", "ai", "agent":
            return "Llm"
        case "heuristic", "default", "corroboration":
            return "Heuristic"
        case let value? where !value.isEmpty:
            return value.replacingOccurrences(of: "_", with: " ").capitalized
        default:
            return "Heuristic"
        }
    }

    /// The statements list's state — pure so the empty/loading/list rule is
    /// testable without a rendered view. An empty result while loading shows the
    /// spinner (never the previous entity's rows); an empty result once loaded
    /// shows the entity-named "no statements" line. (A load error currently reads
    /// as `empty` — ClaimStore surfaces no error yet; `empty.load-error` is a
    /// bounded follow-up.) (spec: kg-entity-inspector, kg.entity.empty.no-claims)
    enum StatementsState: Equatable { case loading, empty, list }

    static func statementsState(isLoading: Bool, isEmpty: Bool) -> StatementsState {
        if isEmpty { return isLoading ? .loading : .empty }
        return .list
    }

    func loadClaims() async {
        isLoading = true
        defer { isLoading = false }
        guard let entityId = entity.id else {
            claims = []
            selectedClaimRowId = nil
            return
        }
        // Route through the observable data layer (#3300) so a mutation anywhere
        // resyncs here; fall back to a direct fetch only when no store is in the
        // environment (the digest also renders in panes that don't carry it).
        if let claimStore {
            await claimStore.loadClaims(forEntity: entityId, force: true)
            claims = claimStore.claims
        } else {
            do {
                claims = try await entityService.listClaims(entityId: entityId, limit: 500)
            } catch {
                claims = []
            }
        }
        selectedClaimRowId = nil
    }
}
