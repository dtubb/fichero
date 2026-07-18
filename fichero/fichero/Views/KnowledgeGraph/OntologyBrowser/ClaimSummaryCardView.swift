#if canImport(AppKit)
import AppKit
#endif
import FicheroAPIClient
import SwiftUI

// MARK: - Claim Summary Card

/// True when a value is a bare UUID / hash with no human-readable content
/// — e.g. `31a6d4d2…519710`. The extractor occasionally leaves a raw
/// source-annotation id in subject/object; we never want to render that as
/// an SVO chip. (#1864)
private func isOpaqueIdentifier(_ value: String) -> Bool {
    let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
    guard trimmed.count >= 16 else { return false }
    let hexAndDashes = CharacterSet(charactersIn: "0123456789abcdefABCDEF-")
    return trimmed.rangeOfCharacter(from: hexAndDashes.inverted) == nil
}

// swiftlint:disable:next type_body_length
struct ClaimSummaryCard: View {
    let claim: Components.Schemas.KnowledgeClaim
    var focusedEntityId: String?
    var onNavigateToSource: ((Components.Schemas.KnowledgeClaim) -> Void)?

    /// Per-window request buses (#3437); optional → safe no-op when a host
    /// hasn't injected them. Read in the +Details.swift extension's handlers.
    @Environment(EntitySearchState.self) var entitySearchState: EntitySearchState?
    @Environment(ClaimSourceNavigationState.self) var claimSourceNavigationState: ClaimSourceNavigationState?
    /// For the source-region crop popover (#2105/#3449); optional so hosts that
    /// don't inject it degrade gracefully.
    @Environment(AnnotationStore.self) var annotationStore: AnnotationStore?

    /// Expanded → reveals the verbatim source excerpt + fetches
    /// contradictions + evidence-chain. Collapsed by default to keep
    /// the card tight. Was previously rendering excerpt always +
    /// duplicating claim.text — see #979.
    @State var isExpanded: Bool = false
    @State var contradictions: [Components.Schemas.ContradictionEvidence]?
    @State var evidenceChain: Components.Schemas.EvidenceChain?
    @State var isLoadingDetails: Bool = false
    @State private var showEditSheet = false
    @State private var showDeleteConfirmation = false
    @State private var isInlineEditing = false
    // Not `private`: written from the mutation handlers in the +Details.swift
    // extension (a separate file), so it must be at least internal.
    @State var mutationError: String?
    @Environment(KGFocusState.self) var kgFocusState
    /// Claim mutations route through the store (#1862); the change-stream fans
    /// the refresh back to every claim surface, retiring the `.ficheroClaim*`
    /// NotificationCenter posts this card used to make.
    @Environment(ClaimStore.self) var claimStore
    /// Finder-style Open in New Tab / New Window for claim cards (#1685).
    @Environment(\.openWindow) private var openWindow
    @AppStorage("editor.fontSize") private var defaultFontSize: Double = 13

    struct SVOTriple {
        let subject: String
        let verb: String
        let object: String
    }

    /// SVO triple extracted from `claim.metadata`. The backend extractor
    /// already produces these (see #984; extractors.py:1375-1456 sets
    /// `metadata["subject" / "verb" / "object"]`). When all three are
    /// present, the card renders the S-V-O sentence with the verb
    /// emphasised so the predicate structure is visible at a glance.
    /// When absent, render a "no claim text — regenerate KG" notice
    /// (the maintainer's directive: "if KG is absent, we generate it"; don't
    /// fall back to `claim.text`).
    static func svoTriple(
        for claim: Components.Schemas.KnowledgeClaim
    ) -> SVOTriple? {
        // Prefer the typed top-level fields (#984). Fall back to
        // claim.metadata for one release while existing claim rows
        // get backfilled.
        let subject = (claim.subjectCanonical ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let verb = (claim.predicateVerb ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        let object = (claim.objectPhrase ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
        if !subject.isEmpty, !verb.isEmpty, !object.isEmpty,
           !isOpaqueIdentifier(subject), !isOpaqueIdentifier(object) {
            return SVOTriple(subject: subject, verb: verb, object: object)
        }
        // Legacy metadata fallback.
        guard let dict = claim.metadata?.additionalProperties.value else { return nil }
        let metaSubject = (dict["subject"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let metaVerb = (dict["verb"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let metaObject = (dict["object"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !metaSubject.isEmpty, !metaVerb.isEmpty, !metaObject.isEmpty,
              !isOpaqueIdentifier(metaSubject), !isOpaqueIdentifier(metaObject) else { return nil }
        return SVOTriple(subject: metaSubject, verb: metaVerb, object: metaObject)
    }

    private var svo: SVOTriple? {
        Self.svoTriple(for: claim)
    }

    var bodyTextFont: Font {
        .system(size: CGFloat(defaultFontSize))
    }

    var secondaryTextFont: Font {
        .system(size: CGFloat(max(defaultFontSize - 1, 10)))
    }

    var tertiaryTextFont: Font {
        .system(size: CGFloat(max(defaultFontSize - 2, 9)))
    }

    /// A claim card has no useful content when it has NO SVO triple AND
    /// `claim.text` is just the bare canonical name (or a short noun
    /// fragment that ends with no verb). #986 — the user saw concept
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
        } else if isInlineEditing {
            InlineClaimEditor(
                claim: claim,
                onCancel: { isInlineEditing = false },
                // The editor persists via PATCH; the change-stream's
                // `claim.updated` event refreshes the bound surfaces (#1862),
                // so no NotificationCenter nudge is needed.
                onSave: { _ in isInlineEditing = false }
            )
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

                provenanceBadges

                // Per-card status / kind tags removed — they duplicated the
                // section-header chip strip in EntityDetailView. (#1006)

                if isExpanded {
                    expandedDetailSection
                }
            }
            .padding(10)
            .background(Color(.windowBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .onTapGesture {
                // Cmd-click opens in a new tab, Finder-style (#1685);
                // plain click focuses the claim in place.
                #if os(macOS)
                if NSApp.currentEvent?.modifierFlags.contains(.command) ?? false {
                    openClaimInNewWindow(asTab: true)
                } else {
                    focusClaim()
                }
                #else
                focusClaim()
                #endif
            }
            .onTapGesture(count: 2) { isInlineEditing = true }
            .contextMenu {
                // Finder-style open affordances (#1685). "Open" focuses the
                // claim in this window; New Tab / New Window open a fresh
                // window carrying the focus via the cross-window KGFocusState.
                OpenInMenuItems(
                    open: { focusClaim() },
                    openInNewTab: { openClaimInNewWindow(asTab: true) },
                    openInNewWindow: { openClaimInNewWindow(asTab: false) }
                )
                // Open the claim's SOURCE document itself in a new tab/window
                // (#3582). Nested under "Open Source" so its New Tab/New Window
                // items don't collide with the claim's above; reuses the shared
                // OpenInMenuItems rather than hand-rolling menu items.
                if let sourceDocId = claim.sourceDocumentId, !sourceDocId.isEmpty {
                    Menu("Open Source") {
                        OpenInMenuItems(
                            openInNewTab: { openSourceInNewWindow(sourceDocId, asTab: true) },
                            openInNewWindow: { openSourceInNewWindow(sourceDocId, asTab: false) }
                        )
                    }
                }
                Divider()
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
                Button("Edit claim…") { showEditSheet = true }
                Divider()
                Button("Delete claim…", role: .destructive) {
                    showDeleteConfirmation = true
                }
            }
            .alert("Delete claim?", isPresented: $showDeleteConfirmation) {
                Button("Delete", role: .destructive) { deleteClaim() }
                Button("Cancel", role: .cancel) {}
            } message: {
                Text("This removes the claim from the knowledge graph. Related entities stay in place.")
            }
            .sheet(isPresented: $showEditSheet) {
                // EditClaimSheet persists via PATCH; the change-stream refreshes
                // bound surfaces, so no NotificationCenter nudge is needed (#1862).
                EditClaimSheet(claim: claim) { _ in }
            }
            .alert(
                "Couldn't update claim",
                isPresented: Binding(
                    get: { mutationError != nil },
                    set: { if !$0 { mutationError = nil } }
                ),
                presenting: mutationError
            ) { _ in
                Button("OK", role: .cancel) { mutationError = nil }
            } message: { message in
                Text(message)
            }
        }
    }  // end else (isEmptyContent path)

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
