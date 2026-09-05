import FicheroAPIClient
import SwiftUI

private struct ClaimDeleteActionParams: Encodable {
    let claimId: String

    enum CodingKeys: String, CodingKey {
        case claimId = "claim_id"
    }
}

// MARK: - Attestations (#4672)

/// One place a statement is attested. The backend has carried the
/// multi-source layer all along (`source_ids` + `source_page_labels`,
/// "pages per source") — the client schema decodes it and, until tonight,
/// nothing read it. Daniel: "if a statement happens in two places … it's an
/// ontological layer. not all of it is hooked up."
///
/// Only the PRIMARY attestation carries a verbatim quote and char offsets —
/// the model stores one anchor per claim — so additional rows navigate to
/// their page without a highlight rather than faking one. (The per-row
/// anchor for corroborating extractions is a server gap: `also_extracted_by`
/// keeps provider labels only, the second run's anchor is discarded at
/// write time.)
struct ClaimAttestation: Equatable, Identifiable {
    let documentId: String
    let pageLabel: String?
    /// Verbatim source quote — primary attestation only.
    let quote: String?
    let charStart: Int?
    let charEnd: Int?
    let bbox: [Double]?
    let isPrimary: Bool

    var id: String { "\(documentId)::\(pageLabel ?? "")::\(isPrimary)" }
}

/// One corroborating extraction — another run that produced this same
/// statement, WITH its own anchor when the run recorded one
/// (`metadata.corroborations`, 0f6feeccc). Legacy rows predate the anchor
/// and carry a label only; they render as attribution, not navigation.
/// The same model legitimately appears more than once with different page
/// labels — the same statement read on two pages of one document is the
/// commonest corroboration of all — so rows are never collapsed per model.
struct ClaimCorroboration: Equatable, Identifiable {
    let label: String
    let documentId: String?
    let pageLabel: String?
    let charStart: Int?
    let charEnd: Int?

    var isNavigable: Bool { !(documentId ?? "").isEmpty }
    var id: String { "\(label)::\(documentId ?? "")::\(pageLabel ?? "")::\(charStart ?? -1)" }
}

// MARK: - ClaimSummaryCard Detail Views + Actions

extension ClaimSummaryCard {

    /// Corroborating runs, anchors and all. `metadata.corroborations` rows
    /// (each `{provider, model, document_id, page_label, char_start,
    /// char_end}`) come first; legacy `also_extracted_by` labels that no
    /// corroborations row already accounts for follow as label-only rows —
    /// old rows are not backfillable, and pretending otherwise would invent
    /// anchors.
    static func corroborations(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> [ClaimCorroboration] {
        let metadata = claim.metadata?.additionalProperties.value ?? [:]
        var rows: [ClaimCorroboration] = []
        for raw in (metadata["corroborations"] as? [Any]) ?? [] {
            guard let dict = raw as? [String: Any] else { continue }
            let provider = (dict["provider"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let model = (dict["model"] as? String ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let label = [provider, model].filter { !$0.isEmpty }.joined(separator: "/")
            guard !label.isEmpty else { continue }
            rows.append(ClaimCorroboration(
                label: label,
                documentId: cleanedOptional(dict["document_id"] as? String),
                pageLabel: cleanedOptional(dict["page_label"] as? String),
                charStart: dict["char_start"] as? Int,
                charEnd: dict["char_end"] as? Int
            ))
        }
        let coveredLabels = Set(rows.map(\.label))
        for label in alsoExtractedBy(claim) ?? [] where !coveredLabels.contains(label) {
            rows.append(ClaimCorroboration(
                label: label, documentId: nil, pageLabel: nil,
                charStart: nil, charEnd: nil
            ))
        }
        return rows
    }

    /// Every place this statement is attested, primary first. Additional
    /// sources come from the multi-source fields, zipped index-wise with
    /// their page labels; a missing label is nil, never invented. A source id
    /// that repeats the primary (or an earlier row) is dropped — re-imports
    /// have produced doubled ids and a list that shows the same page twice
    /// reads as two attestations when it is one.
    static func attestations(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> [ClaimAttestation] {
        var rows: [ClaimAttestation] = []
        var seen: Set<String> = []
        let primaryId = (claim.sourceDocumentId ?? "")
            .trimmingCharacters(in: .whitespacesAndNewlines)
        if !primaryId.isEmpty {
            seen.insert(primaryId)
            rows.append(ClaimAttestation(
                documentId: primaryId,
                pageLabel: cleanedOptional(claim.sourcePageLabel),
                quote: cleanedOptional(claim.sourceExcerpt),
                charStart: claim.sourceCharStart,
                charEnd: claim.sourceCharEnd,
                bbox: claim.sourceAnchor?.rect,
                isPrimary: true
            ))
        }
        let ids = claim.sourceIds ?? []
        let labels = claim.sourcePageLabels ?? []
        for (index, rawId) in ids.enumerated() {
            let docId = rawId.trimmingCharacters(in: .whitespacesAndNewlines)
            guard !docId.isEmpty, seen.insert(docId).inserted else { continue }
            rows.append(ClaimAttestation(
                documentId: docId,
                pageLabel: index < labels.count ? cleanedOptional(labels[index]) : nil,
                quote: nil,
                charStart: nil,
                charEnd: nil,
                bbox: nil,
                isPrimary: false
            ))
        }
        return rows
    }

    private static func cleanedOptional(_ value: String?) -> String? {
        let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines)
        return (trimmed?.isEmpty ?? true) ? nil : trimmed
    }
    @ViewBuilder
    var provenanceBadges: some View {
        let badges = Self.provenanceBadges(for: claim)
        if !badges.isEmpty {
            // The badges are the door to the evidence they summarize: tapping
            // the row expands the drawer, where "N places" becomes the
            // attestation list and "Nx corroborated" its attribution footer
            // (#4672). A summary you cannot open is a count, not evidence.
            Button {
                guard !isExpanded else { return }
                isExpanded = true
                Task { await loadDetails() }
            } label: {
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
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .help("Show this statement's evidence — sources, contradictions, attribution")
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
        let docName = documentStore?
            .currentDocuments
            .first(where: { $0.id == docId })?
            .name
        if let docName, !docName.isEmpty {
            Button { navigateToSource() } label: {
                // Render as a link, not a label: accent color + underline
                // + pointing-hand cursor + trailing chevron all advertise
                // tappability. The maintainer: "we only have one source, can't
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
        // page and highlights the annotation span. When the statement is
        // attested in MORE THAN ONE place, the quote becomes the primary row
        // of the attestation list instead, so one statement never renders
        // its evidence in two competing shapes.
        if attestationRows.count > 1 {
            attestationList
        } else if let excerpt = cleanedDisplayText(claim.sourceExcerpt),
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
        corroborationSection
        // Source-region quick-look (#2105/#3449): the cropped evidence + verbatim
        // span + attribution in a popover, and a Reveal that drives the Preview
        // pane to the page/bbox. Only when we can build a source anchor.
        if let request = Self.openClaimSourceRequest(for: claim) {
            SourceProvenanceChip(
                request: request,
                attribution: ClaimAttribution(claim: claim),
                fetch: { try await annotationStore?.cropRegion($0) ?? nil },
                onReveal: { openClaimSource() }
            )
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

    var attestationRows: [ClaimAttestation] {
        Self.attestations(for: claim)
    }

    /// Every place this statement is attested, each row a door to ITS page.
    /// The primary row carries the verbatim quote and lands with the passage
    /// lit; additional rows navigate without a highlight — the model stores
    /// one anchor, and drawing a guess would claim precision the row does
    /// not have. Extractor attribution renders as a footer: the labels in
    /// `also_extracted_by` name who else produced this statement, but carry
    /// no anchor of their own (server gap), so they are attribution, not
    /// navigation.
    @ViewBuilder
    var attestationList: some View {
        let rows = attestationRows
        VStack(alignment: .leading, spacing: 4) {
            Text("Attested in \(rows.count) places")
                .font(tertiaryTextFont)
                .fontWeight(.semibold)
                .foregroundStyle(.secondary)
            ForEach(rows) { attestation in
                Button {
                    if let request = Self.openClaimSourceRequest(
                        documentId: attestation.documentId,
                        pageLabel: attestation.pageLabel,
                        charStart: attestation.charStart,
                        charEnd: attestation.charEnd,
                        claimId: claim.id,
                        excerpt: attestation.quote,
                        bbox: attestation.bbox
                    ) {
                        claimSourceNavigationState?.request(request)
                    }
                } label: {
                    HStack(alignment: .firstTextBaseline, spacing: 6) {
                        Image(systemName: "doc.text")
                            .font(tertiaryTextFont)
                            .foregroundStyle(Color.accentColor)
                        VStack(alignment: .leading, spacing: 1) {
                            HStack(spacing: 4) {
                                Text(attestationDocName(attestation.documentId))
                                    .font(tertiaryTextFont)
                                    .foregroundStyle(Color.accentColor)
                                    .underline()
                                    .lineLimit(1)
                                    .truncationMode(.middle)
                                if let pageLabel = attestation.pageLabel {
                                    Text("p. \(pageLabel)")
                                        .font(tertiaryTextFont)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            if let quote = attestation.quote.flatMap(cleanedDisplayText) {
                                Text("\"\(quote)\"")
                                    .font(tertiaryTextFont)
                                    .italic()
                                    .foregroundStyle(.secondary)
                                    .lineLimit(2)
                            }
                        }
                        Spacer(minLength: 0)
                    }
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .help(attestation.quote == nil
                    ? "Open this source page"
                    : "Open this source page and highlight the passage")
            }
        }
    }

    /// Corroborating extractions — "also found by …" — rendered wherever
    /// they exist, whether or not the statement is multi-place. Rows with an
    /// anchor are doors to their page (0f6feeccc); legacy label-only rows
    /// render as plain attribution, because their anchors were never
    /// recorded and cannot be invented.
    @ViewBuilder
    var corroborationSection: some View {
        let rows = Self.corroborations(for: claim)
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 3) {
                Text("Also found by")
                    .font(tertiaryTextFont)
                    .fontWeight(.semibold)
                    .foregroundStyle(.secondary)
                ForEach(rows) { corroboration in
                    if corroboration.isNavigable, let docId = corroboration.documentId {
                        Button {
                            if let request = Self.openClaimSourceRequest(
                                documentId: docId,
                                pageLabel: corroboration.pageLabel,
                                charStart: corroboration.charStart,
                                charEnd: corroboration.charEnd,
                                claimId: claim.id
                            ) {
                                claimSourceNavigationState?.request(request)
                            }
                        } label: {
                            HStack(spacing: 4) {
                                Text(corroboration.label)
                                    .font(tertiaryTextFont)
                                    .foregroundStyle(Color.accentColor)
                                    .underline()
                                if let pageLabel = corroboration.pageLabel {
                                    Text("p. \(pageLabel)")
                                        .font(tertiaryTextFont)
                                        .foregroundStyle(.secondary)
                                }
                            }
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .help("Open the page where this run found the statement")
                    } else {
                        Text(corroboration.label)
                            .font(tertiaryTextFont)
                            .foregroundStyle(.tertiary)
                            .help("Recorded before corroborations carried anchors — attribution only")
                    }
                }
            }
        }
    }

    /// Doc name for an attestation row — the owning-library stores, same
    /// resolution the digest uses (#4461); the raw id only when the document
    /// is genuinely absent everywhere.
    func attestationDocName(_ docId: String) -> String {
        let all = (documentStore?.currentDocuments ?? [])
            + (documentStore?.collections ?? [])
            + (documentStore?.sidebarDocuments ?? [])
        return all.first(where: { $0.id == docId })?.name ?? docId
    }

    /// Provider/model labels of OTHER runs that produced this same statement.
    /// Labels only — their anchors were discarded at write time (server gap,
    /// #4672), so this is attribution, not navigation.
    static func alsoExtractedBy(
        _ claim: Components.Schemas.KnowledgeClaim
    ) -> [String]? {
        guard let metadata = claim.metadata?.additionalProperties.value,
              let raw = metadata["also_extracted_by"] as? [Any]
        else { return nil }
        let labels = raw.compactMap { $0 as? String }.filter { !$0.isEmpty }
        return labels.isEmpty ? nil : labels
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
        guard let claimId = claim.id, let entityService else { return }
        isLoadingDetails = true
        defer { isLoadingDetails = false }
        async let contradictionsAsync = try? entityService.contradictions(claimId: claimId)
        async let evidenceChainAsync = try? entityService.evidenceChain(claimId: claimId)
        let cons = await contradictionsAsync ?? []
        let chain = await evidenceChainAsync
        contradictions = cons
        evidenceChain = chain
    }

    // `focusEntityLozenge(named:)` deleted 2026-09-04: its last caller went
    // away and it had been dead since — a resolve-name-to-entity path nothing
    // reached. The live name→entity affordances are the header links (#882)
    // and EntityLozenge's scoped search.

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
        excerpt: String? = nil,
        bbox: [Double]? = nil
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
            charEnd: charEnd,
            bbox: bbox.flatMap { $0.isEmpty ? nil : $0 }
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
            excerpt: claim.sourceExcerpt,
            bbox: claim.sourceAnchor?.rect
        )
    }

    func postOpenClaimSource(for claim: Components.Schemas.KnowledgeClaim) {
        // The claim's source page does NOT have to be in the folder you are
        // looking at (#4666). This used to require the source document to be
        // present in `documentStore.currentDocuments`, so following a
        // statement worked only when its page happened to be in the current
        // listing — which, for a claim read off page 533 of a bundle while you
        // browse the entity list, it never is. The request is resolved against
        // the engine (`revealResolvedSource`, which walks a page child to its
        // parent file), so the listing has no business gating it: the guard
        // turned "go to the source" into silence.
        let docId = claim.sourceDocumentId ?? ""
        guard !docId.isEmpty,
              let request = Self.openClaimSourceRequest(for: claim)
        else { return }
        claimSourceNavigationState?.request(request)
    }

    // Internal, not `private`: `ClaimSummaryCard` spans two files, and Swift's
    // `private` is file-scoped — see this file's header. The tap handler in
    // ClaimSummaryCardView.swift calls it.
    func navigateToSource() {
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
                _ = try await library.actionsService.invokeAction(
                    name: "claim.delete",
                    params: ClaimDeleteActionParams(claimId: claimId)
                )
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
