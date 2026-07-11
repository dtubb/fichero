import FicheroAPIClient
import SwiftUI

private struct ClaimDeleteActionParams: Encodable {
    let claimId: String

    enum CodingKeys: String, CodingKey {
        case claimId = "claim_id"
    }
}

// MARK: - ClaimSummaryCard Detail Views + Actions

extension ClaimSummaryCard {
    @ViewBuilder
    var provenanceBadges: some View {
        let badges = Self.provenanceBadges(for: claim)
        if !badges.isEmpty {
            HStack(spacing: 6) {
                ForEach(Array(badges.enumerated()), id: \.offset) { _, badge in
                    Text(badge.label)
                        .font(tertiaryTextFont)
                        .padding(.horizontal, 7)
                        .padding(.vertical, 3)
                        .background(badge.tint.opacity(0.14), in: Capsule())
                        .foregroundStyle(badge.tint)
                }
                Spacer(minLength: 0)
            }
        }
    }

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
                #if os(macOS)
                if isHovering {
                    NSCursor.pointingHand.set()
                } else {
                    NSCursor.arrow.set()
                }
                #endif
            }
            .help("Open the source document — \(docName)\(pageLabel.map { ", page \($0)" } ?? "")")
        }
    }

    /// Inline detail panel — verbatim source excerpt (moved here from
    /// always-on per #979) + contradictions + evidence-chain summary.
    @ViewBuilder
    var expandedDetailSection: some View {
        Divider()
        // Who asserts this claim — the document itself or a person in the
        // archive — surfaced + editable (#3448).
        ClaimAttributionView(
            attribution: ClaimAttribution(claim: claim),
            onSetSpeaker: { name in
                guard let claimId = claim.id else { return }
                _ = try? await claimStore.patch(claimId: claimId, speakerName: name)
            }
        )
        if let claimText = cleanedDisplayText(claim.text) {
            VStack(alignment: .leading, spacing: 3) {
                Text("Source claim")
                    .font(tertiaryTextFont)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
                Text(claimText)
                    .font(secondaryTextFont)
                    .foregroundStyle(.primary)
                    .lineLimit(nil)
                    .textSelection(.enabled)
            }
        }
        // Verbatim source quote — moved into the expanded drawer so the
        // collapsed card stays tight. Tapping the quote opens the source
        // page and highlights the annotation span.
        if let excerpt = cleanedDisplayText(claim.sourceExcerpt),
           excerpt != claim.text {
            Button {
                openClaimSource()
            } label: {
                Text("\"\(excerpt)\"")
                    .font(secondaryTextFont)
                    .italic()
                    .foregroundStyle(.secondary)
                    .lineLimit(nil)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)
            .help("Open the source page and highlight this annotation")
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

    /// Resolve a lozenge label to an entity and focus its KG neighborhood.
    /// Falls back to the existing text-search event when no exact entity
    /// match exists in the library.
    func focusEntityLozenge(named rawName: String) async {
        let name = rawName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        guard let library = LibraryManager.shared.globalLibrary else {
            entitySearchState?.request(name: name, entityType: nil)
            return
        }
        do {
            let results = try await library.entityService.listEntities(
                query: name,
                limit: 25
            )
            let exact = results.first { entity in
                entity.canonicalName.compare(name, options: [.caseInsensitive, .diacriticInsensitive]) == .orderedSame
            }
            if let exact {
                kgFocusState.focusEntity(entityId: exact.id)
                return
            }
        } catch {
            // Fallback to text search below.
        }
        entitySearchState?.request(name: name, entityType: nil)
    }

    /// Route the explicit source-line button through the typed source-open state.
    func openClaimSource() {
        postOpenClaimSource(for: claim)
    }

    static func openClaimSourceRequest(
        documentId: String,
        pageLabel: String? = nil,
        charStart: Int? = nil,
        charEnd: Int? = nil,
        claimId: String? = nil,
        excerpt: String? = nil
    ) -> ClaimSourceNavigationRequest? {
        guard !documentId.isEmpty else { return nil }
        let cleanedPageLabel = pageLabel?.trimmingCharacters(in: .whitespacesAndNewlines)
        let cleanedExcerpt = excerpt?.trimmingCharacters(in: .whitespacesAndNewlines)
        return ClaimSourceNavigationRequest(
            documentId: documentId,
            claimId: claimId,
            claimText: cleanedExcerpt?.isEmpty == false ? cleanedExcerpt : nil,
            pageLabel: cleanedPageLabel?.isEmpty == false ? cleanedPageLabel : nil,
            charStart: charStart,
            charEnd: charEnd
        )
    }

    static func openClaimSourceRequest(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> ClaimSourceNavigationRequest? {
        openClaimSourceRequest(
            documentId: claim.sourceDocumentId ?? "",
            pageLabel: claim.sourcePageLabel,
            charStart: claim.sourceCharStart,
            charEnd: claim.sourceCharEnd,
            claimId: claim.id,
            excerpt: claim.sourceExcerpt
        )
    }

    func postOpenClaimSource(for claim: Components.Schemas.KnowledgeClaim) {
        let docId = claim.sourceDocumentId ?? ""
        guard !docId.isEmpty,
              LibraryManager.shared.globalLibrary?
                .documentStore
                .currentDocuments
                .contains(where: { $0.id == docId }) == true,
              let request = Self.openClaimSourceRequest(for: claim)
        else { return }
        claimSourceNavigationState?.request(request)
    }

    private func navigateToSource() {
        if let onNavigateToSource {
            onNavigateToSource(claim)
        } else {
            openClaimSource()
        }
    }

    func deleteClaim() {
        guard let claimId = claim.id else { return }
        let libraryId = LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId
        guard let library = LibraryManager.shared.getLibrary(id: libraryId) else { return }
        Task {
            do {
                let result = try await library.actionsService.invokeAction(
                    name: "claim.delete",
                    params: ClaimDeleteActionParams(claimId: claimId)
                )
                LastAction.shared.record(auditId: result.auditId, actionName: "claim.delete")
            } catch {
                mutationError = error.localizedDescription
            }
        }
    }

    /// PATCH the epistemic_status field on this claim. (#901)
    func updateStatus(_ status: Components.Schemas.EpistemicStatus) async {
        guard let claimId = claim.id else { return }
        do {
            // Store-routed PATCH; `claim.updated` from the change-stream
            // refreshes the bound surfaces (#1862).
            _ = try await claimStore.patch(claimId: claimId, epistemicStatus: status)
        } catch {
            mutationError = error.localizedDescription
        }
    }

    /// PATCH the curation_state field on this claim. (#901)
    func updateCuration(_ state: Components.Schemas.ClaimCurationState) async {
        guard let claimId = claim.id else { return }
        do {
            _ = try await claimStore.patch(claimId: claimId, curationState: state)
        } catch {
            mutationError = error.localizedDescription
        }
    }
}
