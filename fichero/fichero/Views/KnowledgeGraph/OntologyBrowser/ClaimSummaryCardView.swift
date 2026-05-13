import FicheroAPIClient
import SwiftUI

// MARK: - Claim Summary Card

struct ClaimSummaryCard: View {
    let claim: Components.Schemas.KnowledgeClaim

    /// Expanded → reveals the verbatim source excerpt + fetches
    /// contradictions + evidence-chain. Collapsed by default to keep
    /// the card tight. Was previously rendering excerpt always +
    /// duplicating claim.text — see #979.
    @State private var isExpanded: Bool = false
    @State private var contradictions: [Components.Schemas.ContradictionEvidence]?
    @State private var evidenceChain: Components.Schemas.EvidenceChain?
    @State private var isLoadingDetails: Bool = false

    /// SVO triple extracted from `claim.metadata`. The backend extractor
    /// already produces these (see #984; extractors.py:1375-1456 sets
    /// `metadata["subject" / "verb" / "object"]`). When all three are
    /// present, the card renders the S-V-O sentence with the verb
    /// emphasised so the predicate structure is visible at a glance.
    /// When absent, render a "no claim text — regenerate KG" notice
    /// (Daniel's directive: "if KG is absent, we generate it"; don't
    /// fall back to `claim.text`).
    private var svo: (subject: String, verb: String, object: String)? {
        guard let dict = claim.metadata?.additionalProperties.value else { return nil }
        let subject = (dict["subject"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let verb = (dict["verb"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let object = (dict["object"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !subject.isEmpty, !verb.isEmpty, !object.isEmpty else { return nil }
        return (subject, verb, object)
    }

    /// A claim card has no useful content when it has NO SVO triple AND
    /// `claim.text` is just the bare canonical name (or a short noun
    /// fragment that ends with no verb). #986 — Daniel saw concept
    /// claims that surfaced as just the entity name + a garbled
    /// source excerpt with no actual claim content. Render-suppress
    /// these rather than poison the inspector.
    private var isEmptyContent: Bool {
        if svo != nil { return false }
        let text = claim.text.trimmingCharacters(in: .whitespacesAndNewlines)
        // Bare canonical name (no punctuation = no composed sentence).
        let lacksSentenceShape = !text.contains(" ") && !text.contains(":")
        return text.isEmpty || lacksSentenceShape
    }

    var body: some View {
        // Suppress entirely when there's nothing meaningful to render —
        // no SVO and the claim.text is just the entity name. (#986)
        if isEmptyContent {
            EmptyView()
        } else {
            VStack(alignment: .leading, spacing: 6) {
            HStack(alignment: .top) {
                claimSentence
                    .textSelection(.enabled)
                Spacer(minLength: 0)
                Button {
                    isExpanded.toggle()
                    if isExpanded {
                        Task { await loadDetails() }
                    }
                } label: {
                    Image(systemName: isExpanded ? "chevron.up" : "chevron.down")
                        .foregroundStyle(.secondary)
                        .font(.caption2)
                }
                .buttonStyle(.plain)
                .help(isExpanded ? "Hide details" : "Show source, contradictions, evidence chain")
            }

            // Source-doc citation — italic doc name + page label,
            // tappable to navigate. The whole point of the KG is to get
            // back to source (#982). (#978/#979)
            sourceLine

            HStack(spacing: 8) {
                if let claimType = claim.claimType {
                    Text(claimType.rawValue.capitalized)
                        .font(.caption2)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(Color.gray.opacity(0.2))
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }

                if let epistemicStatus = claim.epistemicStatus {
                    Text(epistemicStatus.rawValue.capitalized)
                        .font(.caption2)
                        .padding(.horizontal, 4)
                        .padding(.vertical, 2)
                        .background(statusColor.opacity(0.2))
                        .foregroundStyle(statusColor)
                        .clipShape(RoundedRectangle(cornerRadius: 3))
                }
            }

            if isExpanded {
                expandedDetailSection
            }
        }
        .padding(10)
        .background(Color(.windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
        .contextMenu {
            // Status sub-menu — set epistemic_status via PATCH.
            // Confirmed / Tentative / Rejected are the three states the
            // extractor emits; this lets the user override after review.
            // (#901 inline editing.)
            Menu("Set status") {
                Button("Confirmed") { Task { await updateStatus(.confirmed) } }
                Button("Tentative") { Task { await updateStatus(.tentative) } }
                Button("Rejected") { Task { await updateStatus(.rejected) } }
            }
            // Curation state — independent of epistemic status (the
            // extractor's confidence in the source) and tracks the
            // human's review pass.
            Menu("Set curation") {
                Button("Unreviewed") { Task { await updateCuration(.unreviewed) } }
                Button("Shortlisted") { Task { await updateCuration(.shortlisted) } }
                Button("Curated") { Task { await updateCuration(.curated) } }
                Button("Rejected") { Task { await updateCuration(.rejected) } }
            }
            Divider()
            Button("Delete claim…", role: .destructive) {
                deleteClaim()
            }
        }
        }  // end else (isEmptyContent path)
    }

    /// PATCH the epistemic_status field on this claim. (#901)
    private func updateStatus(_ status: Components.Schemas.EpistemicStatus) async {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.globalLibrary else { return }
        do {
            _ = try await library.entityService.patchClaim(
                claimId,
                epistemicStatus: status
            )
            // Notify so EntityDetailView reloads claim list with new
            // chip color. Same channel the delete action uses.
            NotificationCenter.default.post(
                name: .ficheroClaimDeleted,
                object: claimId,
                userInfo: ["action": "patched"]
            )
        } catch {
            NotificationCenter.default.post(
                name: .ficheroClaimDeleted,
                object: nil,
                userInfo: ["error": error.localizedDescription]
            )
        }
    }

    /// PATCH the curation_state field on this claim. (#901)
    private func updateCuration(_ state: Components.Schemas.ClaimCurationState) async {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.globalLibrary else { return }
        do {
            _ = try await library.entityService.patchClaim(
                claimId,
                curationState: state
            )
            NotificationCenter.default.post(
                name: .ficheroClaimDeleted,
                object: claimId,
                userInfo: ["action": "patched"]
            )
        } catch {
            NotificationCenter.default.post(
                name: .ficheroClaimDeleted,
                object: nil,
                userInfo: ["error": error.localizedDescription]
            )
        }
    }

    /// The headline of the card. When SVO metadata is present, render
    /// it as `subject **verb** object` so the predicate is visible at a
    /// glance. When absent, surface a "KG not generated" hint instead
    /// of falling back to `claim.text` — per Daniel's directive, we
    /// want to show the KG, not the loose extractor text. (#978/#986)
    @ViewBuilder
    private var claimSentence: some View {
        if let svo {
            (
                Text(svo.subject)
                + Text(" \(svo.verb) ").italic().foregroundColor(.accentColor)
                + Text(svo.object)
            )
            .font(.caption)
            .lineLimit(isExpanded ? nil : 3)
        } else {
            HStack(spacing: 4) {
                Image(systemName: "questionmark.circle")
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
                Text("No subject-verb-object — regenerate KG?")
                    .font(.caption)
                    .foregroundStyle(.tertiary)
                    .italic()
            }
        }
    }

    /// Italic source-doc name + optional page label, tappable to open
    /// the source. Always renders when the doc exists in the in-memory
    /// store; missing doc is silently hidden (claim was extracted from
    /// a document no longer in the current scope). (#978/#979)
    @ViewBuilder
    private var sourceLine: some View {
        let docId = claim.sourceDocumentId
        let pageLabel = claim.sourcePageLabel?.trimmingCharacters(in: .whitespacesAndNewlines)
        let docName = LibraryManager.shared.globalLibrary?
            .documentStore
            .currentDocuments
            .first(where: { $0.id == docId })?
            .name
        if let docName, !docName.isEmpty {
            Button {
                var info: [String: Any] = ["documentId": docId]
                if let pageLabel, !pageLabel.isEmpty {
                    info["pageLabel"] = pageLabel
                }
                if let start = claim.sourceCharStart { info["charStart"] = start }
                if let end = claim.sourceCharEnd { info["charEnd"] = end }
                if let claimId = claim.id { info["claimId"] = claimId }
                // Forward the verbatim excerpt so the PDF highlight
                // overlay can findString it on the target page (#995).
                if let excerpt = claim.sourceExcerpt?
                    .trimmingCharacters(in: .whitespacesAndNewlines),
                   !excerpt.isEmpty {
                    info["excerpt"] = excerpt
                }
                NotificationCenter.default.post(
                    name: .ficheroOpenClaimSource,
                    object: nil,
                    userInfo: info
                )
            } label: {
                HStack(spacing: 4) {
                    Image(systemName: "doc.text")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Text(docName)
                        .font(.caption2)
                        .italic()
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    if let pageLabel, !pageLabel.isEmpty {
                        Text("p. \(pageLabel)")
                            .font(.caption2)
                            .foregroundStyle(.tertiary)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)
            .help("Open the source document")
        }
    }

    /// Inline detail panel — verbatim source excerpt (moved here from
    /// always-on per #979) + contradictions + evidence-chain summary.
    /// Lights up the post-1587a1b6 claim-analysis surface inside the
    /// existing OntologyBrowser shell so the new backend has UI today.
    @ViewBuilder
    private var expandedDetailSection: some View {
        Divider()
        // Verbatim source quote — moved into the expanded drawer so the
        // collapsed card stays tight. Tapping the quote runs a library
        // text-search via the existing entity-lozenge pathway. (#979)
        if let excerpt = claim.sourceExcerpt?.trimmingCharacters(in: .whitespacesAndNewlines),
           !excerpt.isEmpty,
           excerpt != claim.text {
            Button {
                NotificationCenter.default.post(
                    name: .ficheroEntitySearchRequested,
                    object: nil,
                    userInfo: ["name": excerpt]
                )
            } label: {
                Text("“\(excerpt)”")
                    .font(.caption2)
                    .italic()
                    .foregroundStyle(.secondary)
                    .lineLimit(nil)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)
            .help("Search the library for this quote")
        }
        if isLoadingDetails {
            HStack {
                ProgressView().scaleEffect(0.6)
                Text("Loading analysis…")
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
        } else {
            VStack(alignment: .leading, spacing: 4) {
                if let cons = contradictions, !cons.isEmpty {
                    Label("\(cons.count) contradiction\(cons.count == 1 ? "" : "s")",
                          systemImage: "exclamationmark.triangle")
                        .font(.caption2)
                        .foregroundStyle(.red)
                    ForEach(Array(cons.prefix(3).enumerated()), id: \.offset) { _, contradiction in
                        Text("• \(contradiction.contradictingText)")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                } else {
                    Label("No contradictions recorded", systemImage: "checkmark.seal")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                if let chain = evidenceChain {
                    let linkCount = chain.relatedClaims.count
                    let sourceCount = chain.sources.count
                    Label(
                        "\(sourceCount) source\(sourceCount == 1 ? "" : "s"), \(linkCount) related claim\(linkCount == 1 ? "" : "s")",
                        systemImage: "link"
                    )
                    .font(.caption2)
                    .foregroundStyle(.secondary)
                }
            }
        }
    }

    private func loadDetails() async {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.globalLibrary else { return }
        isLoadingDetails = true
        defer { isLoadingDetails = false }
        async let contradictionsAsync = try? library.entityService.contradictions(claimId: claimId)
        async let evidenceChainAsync = try? library.entityService.evidenceChain(claimId: claimId)
        let cons = await contradictionsAsync ?? []
        let chain = await evidenceChainAsync
        contradictions = cons
        evidenceChain = chain
    }

    fileprivate func deleteClaim() {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.globalLibrary else { return }
        Task {
            do {
                try await library.entityService.deleteClaim(claimId)
                NotificationCenter.default.post(name: .ficheroClaimDeleted, object: claimId)
            } catch {
                NotificationCenter.default.post(
                    name: .ficheroClaimDeleted,
                    object: nil,
                    userInfo: ["error": error.localizedDescription]
                )
            }
        }
    }

    private var statusColor: Color {
        guard let status = claim.epistemicStatus else { return .gray }
        switch status {
        case .confirmed: return .green
        case .rejected: return .red
        case .tentative: return .orange
        }
    }
}
