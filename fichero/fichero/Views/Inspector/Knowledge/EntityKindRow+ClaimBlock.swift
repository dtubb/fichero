import FicheroAPIClient
import SwiftUI

// MARK: - EntityKindRow claim rendering

extension EntityKindRow {
    var bodyTextFont: Font {
        .system(size: CGFloat(defaultFontSize))
    }

    var secondaryTextFont: Font {
        .system(size: CGFloat(max(defaultFontSize - 1, 10)))
    }

    var primaryClaim: Components.Schemas.KnowledgeClaim? {
        claimById[item.claimId]
    }

    /// Aliases + page reference rendered as one selectable text run,
    /// sitting beside the tappable name on line 1.
    var trailingText: Text {
        let aliasesText = item.aliases.isEmpty ? "" : " (aka \(item.aliases.joined(separator: ", ")))"
        let pageRefText = (showPageRef ? pageReference : nil).map { "  (\($0))" } ?? ""
        if !item.aliases.isEmpty {
            return Text("\(aliasesText)\(pageRefText)")
                .font(secondaryTextFont)
                .foregroundStyle(.secondary)
        }
        return Text(pageRefText)
            .font(secondaryTextFont)
            .foregroundStyle(.secondary)
    }

    /// Scholarly-style page reference: prefer the recorded label
    /// (e.g. "page 4", "folio 12r"); strip a leading "page " so we can
    /// abbreviate it to "p. 4". Returns nil when no label is available
    /// (don't fabricate a reference from nothing).
    var pageReference: String? {
        guard let raw = item.sourcePageLabel?.trimmingCharacters(in: .whitespaces),
              !raw.isEmpty
        else { return nil }
        let lower = raw.lowercased()
        if lower.hasPrefix("page "), let numericPart = lower.split(separator: " ").last {
            return "p. \(numericPart)"
        }
        return raw
    }

    @ViewBuilder
    // swiftlint:disable:next function_parameter_count
    func claimBlock(
        claimId: String,
        context: String,
        sourceDocumentId: String?,
        sourcePageLabel: String?,
        sourceExcerpt: String?,
        confidence: Double?,
        isPrimary: Bool
    ) -> some View {
        let claim = claimById[claimId]
        let isFocused = claimFocusState.isClaimSelected(claimId)

        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .firstTextBaseline, spacing: 6) {
                claimNameOrLabel(claim: claim, isFocused: isFocused, isPrimary: isPrimary)

                claimBadges(claim: claim, confidence: confidence, isPrimary: isPrimary)

                if isPrimary, let onClaimSelect = onClaimSelect {
                    claimSelectButton(
                        claimId: claimId,
                        sourceDocumentId: sourceDocumentId,
                        sourcePageLabel: sourcePageLabel,
                        sourceExcerpt: sourceExcerpt,
                        onClaimSelect: onClaimSelect
                    )
                }

                if isPrimary {
                    claimSourceButton(
                        claimId: claimId,
                        sourceDocumentId: sourceDocumentId,
                        sourcePageLabel: sourcePageLabel,
                        sourceExcerpt: sourceExcerpt
                    )
                }
            }

            claimContextText(context: context)

            claimExcerptButton(sourceExcerpt: sourceExcerpt, context: context)

            // Inline S/V/O editor (#3463): "Edit S/V/O…" expands the row in place
            // into editable subject / verb / object fields (reusing the shared
            // InlineClaimEditor, which persists via the claim.patch action; the
            // change stream refreshes the list). Primary claim only.
            claimInlineEditor(claimId: claimId, claim: claim, isPrimary: isPrimary)
        }
        .padding(.horizontal, 6)
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        // Single-click selection + arrow-key nav are owned by the enclosing
        // native List(selection:) (#3425). Double-click still opens — focus the
        // claim and jump to its source page, Finder-style. (#1864/#1865)
        .simultaneousGesture(
            TapGesture(count: 2).onEnded {
                openClaim(claimId: claimId, sourceDocumentId: sourceDocumentId)
            }
        )
        .contextMenu {
            claimContextMenuContent(claimId: claimId, claim: claim, isPrimary: isPrimary)
        }
    }

    /// Primary rows show the tappable name + trailing aliases/page-ref;
    /// secondary (related-claim) rows show a plain label instead.
    @ViewBuilder
    private func claimNameOrLabel(
        claim: Components.Schemas.KnowledgeClaim?,
        isFocused: Bool,
        isPrimary: Bool
    ) -> some View {
        if isPrimary {
            Button(action: {
                if let claim {
                    handleClaimTap(claim)
                } else {
                    focusPrimaryClaim()
                }
            }, label: {
                Text(item.displayName)
                    .font(bodyTextFont)
                    .fontWeight(.medium)
                    .foregroundStyle(isFocused ? Color.accentColor : Color.primary)
            })
            .buttonStyle(.plain)
            .help("Focus \"\(item.displayName)\"")
            .accessibilityHint("Focuses this \(kind.label.lowercased())")

            trailingText
                .frame(maxWidth: .infinity, alignment: .leading)
                .textSelection(.enabled)
        } else {
            Text("Related claim")
                .font(secondaryTextFont)
                .foregroundStyle(.secondary)
        }
    }

    /// Curation state + confidence + "includes children" badges.
    @ViewBuilder
    private func claimBadges(
        claim: Components.Schemas.KnowledgeClaim?,
        confidence: Double?,
        isPrimary: Bool
    ) -> some View {
        if let curationState = claim?.curationState, curationState != .unreviewed {
            ClaimCurationBadge(state: curationState)
        }

        // #4394: was `String(format: "%.2f")`, which rendered an uncalibrated
        // model self-report as a two-decimal measurement, unlabelled, in the
        // densest part of the inspector. `recorded` also keeps "no confidence
        // was recorded" rendering as nothing rather than as a number.
        if showConfidence, let band = ConfidenceBand.recorded(confidence) {
            Text(band.badgeText)
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.secondary.opacity(0.12))
                .clipShape(Capsule())
                .help(band.help)
                .accessibilityLabel(band.help)
        }
        if isPrimary, item.includesChildren {
            Text("Includes children")
                .font(.caption2)
                .foregroundStyle(.secondary)
                .padding(.horizontal, 6)
                .padding(.vertical, 2)
                .background(Color.secondary.opacity(0.12))
                .clipShape(Capsule())
                .help("This row includes claims from child documents")
        }
    }

    /// Star toggle that focuses/selects this claim for highlighting.
    @ViewBuilder
    private func claimSelectButton(
        claimId: String,
        sourceDocumentId: String?,
        sourcePageLabel: String?,
        sourceExcerpt: String?,
        onClaimSelect: @escaping (String, String?, String?, String?, Int?, Int?) -> Void
    ) -> some View {
        let claim = claimById[claimId]
        let isFocused = claimFocusState.isClaimSelected(claimId)
        Button(action: {
            if let claim {
                handleClaimTap(claim)
            } else {
                focusPrimaryClaim()
                onClaimSelect(
                    claimId,
                    sourceExcerpt,
                    sourceDocumentId,
                    sourcePageLabel,
                    nil,
                    nil
                )
            }
        }, label: {
            Image(systemName: isFocused ? "star.fill" : "star")
                .font(.system(size: 12))
                .foregroundStyle(isFocused ? Color.accentColor : Color.secondary)
        })
        .buttonStyle(.plain)
        .help(isFocused ? "Claim selected for highlighting" : "Select claim for highlighting")
        .accessibilityLabel(isFocused ? "Claim selected for highlighting" : "Select claim for highlighting")
    }

    /// "Go to source" arrow with hover/long-press provenance preview popover.
    @ViewBuilder
    private func claimSourceButton(
        claimId: String,
        sourceDocumentId: String?,
        sourcePageLabel: String?,
        sourceExcerpt: String?
    ) -> some View {
        let claim = claimById[claimId]
        if let sourceDocumentId,
           let navigate = onNavigateToSource,
           let request = sourceNavigationRequest(
               claimId: claimId,
               claim: claim,
               sourceDocumentId: sourceDocumentId,
               sourcePageLabel: sourcePageLabel,
               sourceExcerpt: sourceExcerpt
           ) {
            Button {
                navigate(sourceDocumentId)
            } label: {
                Image(systemName: "arrow.right.circle")
                    .font(.body)
                    .foregroundStyle(Color.accentColor)
            }
            .buttonStyle(.plain)
            .help("Go to source — hover or long-press to preview")
            .accessibilityLabel("Go to source")
            .accessibilityHint("Opens the page this claim came from")
            // Source-provenance quick-look (#3449/#2105): hovering the
            // arrow previews the cropped source region + verbatim span in
            // a popover (reusing SourceProvenanceCard → SourceSnippet); the
            // popover's Reveal — or clicking the arrow — drives the Preview
            // pane to the page. Full keyboard (Space) preview lands with the
            // native-List conversion in #3425.
            .onHover { hovering in
                if hovering { isSourcePreviewPresented = true }
            }
            // Touch equivalent of hover-to-preview (#3666): on iPad/iPhone
            // there's no hover, so a long-press opens the same source-
            // provenance popover. `simultaneousGesture` leaves the button's
            // TAP (navigate to source) intact.
            .simultaneousGesture(
                LongPressGesture(minimumDuration: 0.4).onEnded { _ in
                    isSourcePreviewPresented = true
                }
            )
            .popover(isPresented: $isSourcePreviewPresented, arrowEdge: .trailing) {
                SourceProvenanceCard(
                    request: request,
                    attribution: claim.map(ClaimAttribution.init(claim:)),
                    fetch: { try await annotationStore?.cropRegion($0) ?? nil },
                    onReveal: {
                        isSourcePreviewPresented = false
                        navigate(sourceDocumentId)
                    }
                )
            }
        }
    }

    @ViewBuilder
    private func claimContextText(context: String) -> some View {
        if showContext,
           !context.isEmpty,
           context != item.displayName,
           !item.displayName.contains(context) {
            Text(context)
                .font(bodyTextFont)
                .foregroundStyle(.secondary)
                .textSelection(.enabled)
        }
    }

    @ViewBuilder
    private func claimExcerptButton(sourceExcerpt: String?, context: String) -> some View {
        if showExcerpt,
           let excerpt = sourceExcerpt,
           !excerpt.isEmpty,
           excerpt != context,
           excerpt != item.displayName {
            Button {
                entitySearchState?.request(name: excerpt, entityType: nil)
            } label: {
                Text("\u{201C}\(excerpt)\u{201D}")
                    .font(secondaryTextFont)
                    .italic()
                    .foregroundStyle(.secondary)
                    .lineLimit(3)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            .buttonStyle(.plain)
            .help("Search the library for this quote")
        }
    }

    @ViewBuilder
    private func claimInlineEditor(
        claimId: String,
        claim: Components.Schemas.KnowledgeClaim?,
        isPrimary: Bool
    ) -> some View {
        if isPrimary, inlineEditingClaimId == claimId, let claim {
            InlineClaimEditor(
                claim: claim,
                onCancel: { inlineEditingClaimId = nil },
                onSave: { _ in inlineEditingClaimId = nil }
            )
            .padding(.top, 4)
        }
    }

    @ViewBuilder
    private func claimContextMenuContent(
        claimId: String,
        claim: Components.Schemas.KnowledgeClaim?,
        isPrimary: Bool
    ) -> some View {
        if let claim {
            claimBulkContextMenu(for: claim)
            if isPrimary {
                Divider()
            }
        }
        if isPrimary {
            Button(inlineEditingClaimId == claimId ? "Done Editing" : "Edit S/V/O…") {
                inlineEditingClaimId = (inlineEditingClaimId == claimId) ? nil : claimId
            }
            if let entityId = item.entityId {
                Button("Show in Graph") {
                    kgFocusState.requestGraphReveal(entityId: entityId)
                }
            }
        }
    }

    /// Build the source anchor for the provenance popover / reveal. Prefer the
    /// full claim (it carries char range + bbox); fall back to the grouped
    /// item's coarser fields. Reuses `ClaimSummaryCard.openClaimSourceRequest`
    /// so every "show me the source" surface shares one anchor builder (#2105).
    func sourceNavigationRequest(
        claimId: String,
        claim: Components.Schemas.KnowledgeClaim?,
        sourceDocumentId: String,
        sourcePageLabel: String?,
        sourceExcerpt: String?
    ) -> ClaimSourceNavigationRequest? {
        if let claim {
            return ClaimSummaryCard.openClaimSourceRequest(for: claim)
        }
        return ClaimSummaryCard.openClaimSourceRequest(
            documentId: sourceDocumentId,
            pageLabel: sourcePageLabel,
            claimId: claimId,
            excerpt: sourceExcerpt
        )
    }
}
