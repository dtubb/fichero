import AppKit
import FicheroAPIClient
import SwiftUI

// Split out of ClaimSummaryCardView.swift for `file_length` (#4484).
//
// The split was forced by an accessibility label: that file sat at exactly
// 400 lines, so the one line needed to make its expand/collapse control
// announce itself pushed it over. Leaving the control unlabelled to satisfy
// a line count would be a lint rule deciding whether the app is usable with
// VoiceOver — the same shape as #4482, where a builder arity limit had been
// deciding the library's column set.
//
// Pure move: no renames, no signature changes.

// MARK: - Navigation & Sentence

extension ClaimSummaryCard {
    private func focusClaim() {
        kgFocusState.focusClaim(
            claimId: claim.id,
            entityId: focusedEntityId,
            sourceDocumentId: claim.sourceDocumentId,
            sourcePageLabel: claim.sourcePageLabel
        )
    }

    /// Open this claim in a new tab/window (#1685). Reuses the Safari
    /// new-window path; the shared `KGFocusState` carries the focus.
    /// Open the claim's SOURCE document in a native tab (`asTab`) or a new
    /// window (#3582) — the browser-tab metaphor applied to a reveal menu.
    private func openSourceInNewWindow(_ documentId: String, asTab: Bool) {
        let libraryId = LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId
        WindowOpener.open(libraryId: libraryId, documentId: documentId, asTab: asTab, using: openWindow)
    }

    private func openClaimInNewWindow(asTab: Bool) {
        // Follow-up (#1685): like entities, a brand-new window only reacts to
        // focusedClaimId via .onChange, so deterministic auto-focus on first
        // mount would need a one-shot on-appear consumer of KGFocusState.
        focusClaim()
        let libraryId = LibraryManager.shared.currentLibraryId ?? LibraryManager.globalLibraryId
        WindowOpener.open(libraryId: libraryId, asTab: asTab, using: openWindow)
    }

    private func revealSourceClaimInline() {
        isExpanded = true
        Task { await loadDetails() }
        focusClaim()
    }

    private func beginInlineEditing() {
        isInlineEditing = true
    }

    /// The headline of the card. When SVO metadata is present, render
    /// it as three individually-tappable chips with distinct styling for
    /// subject, verb, and object. When absent, surface a "KG not generated" hint instead
    /// of falling back to `claim.text` — per the maintainer's directive, we
    /// want to show the KG, not the loose extractor text. (#978/#986)
    @ViewBuilder
    private var claimSentence: some View {
        if let svo {
            HStack(spacing: 6) {
                // Subject chip — reveal the underlying claim in place.
                Button(action: {
                    revealSourceClaimInline()
                }, label: {
                    Text(svo.subject)
                        .font(bodyTextFont)
                        .fontWeight(.medium)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color(platformColor: .systemGray))
                        .foregroundColor(.primary)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                })
                .buttonStyle(.plain)
                .help("Show the source claim")

                // Verb chip — reveal the underlying claim in place.
                Button(action: {
                    beginInlineEditing()
                }, label: {
                    Text(svo.verb)
                        .font(bodyTextFont)
                        .fontWeight(.semibold)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.accentColor)
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                })
                .buttonStyle(.plain)
                .help("Show the source claim")

                // Object chip — reveal the underlying claim in place.
                Button(action: {
                    beginInlineEditing()
                }, label: {
                    Text(svo.object)
                        .font(bodyTextFont)
                        .fontWeight(.medium)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color(platformColor: .systemGray))
                        .foregroundColor(.primary)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                })
                .buttonStyle(.plain)
                .help("Show the source claim")
            }
            .padding(.vertical, 4)
        } else if let excerpt = cleanedDisplayText(claim.sourceExcerpt) {
            // SVO missing → surface the verbatim source excerpt as the
            // card body so it isn't content-empty. The "regenerate KG"
            // hint moves to a small footer line so the user still
            // knows the SVO is absent. (#1006)
            VStack(alignment: .leading, spacing: 4) {
                Button {
                    openClaimSource()
                } label: {
                    Text(excerpt)
                        .font(bodyTextFont)
                        .lineLimit(isExpanded ? nil : 3)
                        .foregroundStyle(.primary)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .buttonStyle(.plain)
                .help("Open the source page and highlight this annotation")
                HStack(spacing: 4) {
                    Image(systemName: "questionmark.circle")
                        .font(tertiaryTextFont)
                        .foregroundStyle(.tertiary)
                    Text("No subject-verb-object — regenerate KG?")
                        .font(tertiaryTextFont)
                        .foregroundStyle(.tertiary)
                        .italic()
                }
            }
        } else {
            HStack(spacing: 4) {
                Image(systemName: "questionmark.circle")
                    .font(tertiaryTextFont)
                    .foregroundStyle(.tertiary)
                Text("No subject-verb-object — regenerate KG?")
                    .font(secondaryTextFont)
                    .foregroundStyle(.tertiary)
                    .italic()
            }
        }
    }
}
