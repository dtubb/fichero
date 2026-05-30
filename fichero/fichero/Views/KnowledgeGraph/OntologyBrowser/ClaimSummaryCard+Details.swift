import FicheroAPIClient
import SwiftUI

// MARK: - ClaimSummaryCard Detail Views + Actions

extension ClaimSummaryCard {

    /// Italic source-doc name + optional page label, tappable to open
    /// the source. Always renders when the doc exists in the in-memory
    /// store; missing doc is silently hidden (claim was extracted from
    /// a document no longer in the current scope). (#978/#979)
    @ViewBuilder
    var sourceLine: some View {
        let docId = claim.sourceDocumentId
        let pageLabel = claim.sourcePageLabel?.trimmingCharacters(in: .whitespacesAndNewlines)
        let docName = LibraryManager.shared.globalLibrary?
            .documentStore
            .currentDocuments
            .first(where: { $0.id == docId })?
            .name
        if let docName, !docName.isEmpty {
            Button { navigateToSource() } label: {
                // Render as a link, not a label: accent color + underline
                // + pointing-hand cursor + trailing chevron all advertise
                // tappability. Daniel: "we only have one source, can't
                // see it and can't click on it." (#1013)
                HStack(spacing: 4) {
                    Image(systemName: "doc.text")
                        .font(tertiaryTextFont)
                        .foregroundStyle(Color.accentColor)
                    Text(docName)
                        .font(tertiaryTextFont)
                        .underline()
                        .foregroundStyle(Color.accentColor)
                        .lineLimit(1)
                        .truncationMode(.middle)
                    if let pageLabel, !pageLabel.isEmpty {
                        Text("p. \(pageLabel)")
                            .font(tertiaryTextFont)
                            .foregroundStyle(.secondary)
                    }
                    Image(systemName: "chevron.right")
                        .font(.system(size: 9, weight: .semibold))
                        .foregroundStyle(.tertiary)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .onHover { isHovering in
                if isHovering {
                    NSCursor.pointingHand.set()
                } else {
                    NSCursor.arrow.set()
                }
            }
            .help("Open the source document — \(docName)\(pageLabel.map { ", page \($0)" } ?? "")")
        }
    }

    /// Inline detail panel — verbatim source excerpt (moved here from
    /// always-on per #979) + contradictions + evidence-chain summary.
    @ViewBuilder
    var expandedDetailSection: some View {
        Divider()
        // Verbatim source quote — moved into the expanded drawer so the
        // collapsed card stays tight. Tapping the quote runs a library
        // text-search via the existing entity-lozenge pathway. (#979)
        if let excerpt = cleanedDisplayText(claim.sourceExcerpt),
           excerpt != claim.text {
            Button {
                NotificationCenter.default.post(
                    name: .ficheroEntitySearchRequested,
                    object: nil,
                    userInfo: ["name": excerpt]
                )
            } label: {
                Text("\"\(excerpt)\"")
                    .font(secondaryTextFont)
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
                    .font(tertiaryTextFont)
                    .foregroundStyle(.secondary)
            }
        } else {
            VStack(alignment: .leading, spacing: 4) {
                if let cons = contradictions, !cons.isEmpty {
                    Label("\(cons.count) contradiction\(cons.count == 1 ? "" : "s")",
                          systemImage: "exclamationmark.triangle")
                        .font(tertiaryTextFont)
                        .foregroundStyle(.red)
                    ForEach(Array(cons.prefix(3).enumerated()), id: \.offset) { _, contradiction in
                        Text("• \(contradiction.contradictingText)")
                            .font(tertiaryTextFont)
                            .foregroundStyle(.secondary)
                            .lineLimit(2)
                    }
                } else {
                    Label("No contradictions recorded", systemImage: "checkmark.seal")
                        .font(tertiaryTextFont)
                        .foregroundStyle(.secondary)
                }
                if let chain = evidenceChain {
                    let linkCount = chain.relatedClaims.count
                    let sourceCount = chain.sources.count
                    Label(
                        "\(sourceCount) source\(sourceCount == 1 ? "" : "s"), "
                        + "\(linkCount) related claim\(linkCount == 1 ? "" : "s")",
                        systemImage: "link"
                    )
                    .font(tertiaryTextFont)
                    .foregroundStyle(.secondary)
                }
            }
        }
    }

    func cleanedDisplayText(_ value: String?) -> String? {
        guard let raw = value?.trimmingCharacters(in: .whitespacesAndNewlines),
              !raw.isEmpty else { return nil }
        let replacementGlyphs = raw.filter { $0 == "\u{FFFD}" || $0 == "□" || $0 == "�" }
        if !raw.isEmpty {
            let ratio = Double(replacementGlyphs.count) / Double(raw.count)
            if ratio > 0.08 { return nil }
        }
        return raw
    }

    func loadDetails() async {
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

    /// Post ficheroOpenClaimSource for the explicit sourceLine button.
    func openClaimSource() {
        Self.postOpenClaimSource(for: claim)
    }

    static func openClaimSourceUserInfo(
        documentId: String,
        pageLabel: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil,
        claimId: String? = nil,
        excerpt: String? = nil
    ) -> [String: Any]? {
        guard !documentId.isEmpty else { return nil }
        var info: [String: Any] = ["documentId": documentId]
        if let pageLabel = pageLabel?.trimmingCharacters(in: .whitespacesAndNewlines),
           !pageLabel.isEmpty {
            info["pageLabel"] = pageLabel
        }
        if let charStart { info["charStart"] = charStart }
        if let charEnd { info["charEnd"] = charEnd }
        if let claimId { info["claimId"] = claimId }
        if let excerpt = excerpt?.trimmingCharacters(in: .whitespacesAndNewlines),
           !excerpt.isEmpty {
            info["excerpt"] = excerpt
        }
        return info
    }

    static func openClaimSourceUserInfo(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> [String: Any]? {
        openClaimSourceUserInfo(
            documentId: claim.sourceDocumentId,
            pageLabel: claim.sourcePageLabel,
            charStart: claim.sourceCharStart,
            charEnd: claim.sourceCharEnd,
            claimId: claim.id,
            excerpt: claim.sourceExcerpt
        )
    }

    static func postOpenClaimSource(for claim: Components.Schemas.KnowledgeClaim) {
        let docId = claim.sourceDocumentId
        guard !docId.isEmpty,
              LibraryManager.shared.globalLibrary?
                .documentStore
                .currentDocuments
                .contains(where: { $0.id == docId }) == true,
              let info = openClaimSourceUserInfo(for: claim)
        else { return }
        NotificationCenter.default.post(
            name: .ficheroOpenClaimSource,
            object: nil,
            userInfo: info
        )
    }

    private func navigateToSource() {
        if let onNavigateToSource {
            onNavigateToSource(claim)
        } else {
            openClaimSource()
        }
    }

    func deleteClaim() {
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

    /// PATCH the epistemic_status field on this claim. (#901)
    func updateStatus(_ status: Components.Schemas.EpistemicStatus) async {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.globalLibrary else { return }
        do {
            let updated = try await library.entityService.patchClaim(
                claimId,
                epistemicStatus: status
            )
            NotificationCenter.default.post(
                name: .ficheroClaimUpdated,
                object: updated.id,
                userInfo: ["claim": updated]
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
    func updateCuration(_ state: Components.Schemas.ClaimCurationState) async {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.globalLibrary else { return }
        do {
            let updated = try await library.entityService.patchClaim(
                claimId,
                curationState: state
            )
            NotificationCenter.default.post(
                name: .ficheroClaimUpdated,
                object: updated.id,
                userInfo: ["claim": updated]
            )
        } catch {
            NotificationCenter.default.post(
                name: .ficheroClaimDeleted,
                object: nil,
                userInfo: ["error": error.localizedDescription]
            )
        }
    }
}
