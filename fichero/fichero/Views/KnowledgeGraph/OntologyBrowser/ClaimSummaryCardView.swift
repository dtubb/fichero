import FicheroAPIClient
import SwiftUI

// MARK: - Claim Summary Card

struct ClaimSummaryCard: View {
    let claim: Components.Schemas.KnowledgeClaim
    let onNavigateToSource: ((Components.Schemas.KnowledgeClaim) -> Void)? = nil

    /// Expanded → reveals the verbatim source excerpt + fetches
    /// contradictions + evidence-chain. Collapsed by default to keep
    /// the card tight. Was previously rendering excerpt always +
    /// duplicating claim.text — see #979.
    @State var isExpanded: Bool = false
    @State var contradictions: [Components.Schemas.ContradictionEvidence]?
    @State var evidenceChain: Components.Schemas.EvidenceChain?
    @State var isLoadingDetails: Bool = false
    @State private var showEditSheet = false

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
    /// (Daniel's directive: "if KG is absent, we generate it"; don't
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
        if !subject.isEmpty, !verb.isEmpty, !object.isEmpty {
            return SVOTriple(subject: subject, verb: verb, object: object)
        }
        // Legacy metadata fallback.
        guard let dict = claim.metadata?.additionalProperties.value else { return nil }
        let metaSubject = (dict["subject"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let metaVerb = (dict["verb"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        let metaObject = (dict["object"] as? String)?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
        guard !metaSubject.isEmpty, !metaVerb.isEmpty, !metaObject.isEmpty else { return nil }
        return SVOTriple(subject: metaSubject, verb: metaVerb, object: metaObject)
    }

    private var svo: SVOTriple? {
        Self.svoTriple(for: claim)
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

                // Per-card status / kind tags removed — they duplicated the
                // section-header chip strip in EntityDetailView. (#1006)

                if isExpanded {
                    expandedDetailSection
                }
            }
            .padding(10)
            .background(Color(.windowBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .onTapGesture { navigateToSource() }
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
                Button("Edit claim…") { showEditSheet = true }
                Divider()
                Button("Delete claim…", role: .destructive) {
                    deleteClaim()
                }
            }
            .sheet(isPresented: $showEditSheet) {
                EditClaimSheet(claim: claim) { updated in
                    NotificationCenter.default.post(
                        name: .ficheroClaimUpdated,
                        object: updated.id,
                        userInfo: ["claim": updated]
                    )
                }
            }
        }
    }  // end else (isEmptyContent path)
    }

    /// The headline of the card. When SVO metadata is present, render
    /// it as three individually-tappable chips with distinct styling for
    /// subject, verb, and object. When absent, surface a "KG not generated" hint instead
    /// of falling back to `claim.text` — per Daniel's directive, we
    /// want to show the KG, not the loose extractor text. (#978/#986)
    @ViewBuilder
    private var claimSentence: some View {
        if let svo {
            HStack(spacing: 6) {
                // Subject chip — tappable to search for subject entity
                Button(action: {
                    NotificationCenter.default.post(
                        name: .ficheroEntitySearchRequested,
                        object: nil,
                        userInfo: ["name": svo.subject]
                    )
                }, label: {
                    Text(svo.subject)
                        .font(.caption)
                        .fontWeight(.medium)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color(NSColor.systemGray))
                        .foregroundColor(.primary)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                })
                .buttonStyle(.plain)
                .help("Search for '\(svo.subject)' in library")

                // Verb chip — tappable to search for predicate/verb
                Button(action: {
                    NotificationCenter.default.post(
                        name: .ficheroEntitySearchRequested,
                        object: nil,
                        userInfo: ["name": svo.verb]
                    )
                }, label: {
                    Text(svo.verb)
                        .font(.caption)
                        .fontWeight(.semibold)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color.accentColor)
                        .foregroundColor(.white)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                })
                .buttonStyle(.plain)
                .help("Search for '\(svo.verb)' predicates in library")

                // Object chip — tappable to search for object entity
                Button(action: {
                    NotificationCenter.default.post(
                        name: .ficheroEntitySearchRequested,
                        object: nil,
                        userInfo: ["name": svo.object]
                    )
                }, label: {
                    Text(svo.object)
                        .font(.caption)
                        .fontWeight(.medium)
                        .padding(.horizontal, 8)
                        .padding(.vertical, 4)
                        .background(Color(NSColor.systemGray))
                        .foregroundColor(.primary)
                        .clipShape(RoundedRectangle(cornerRadius: 8))
                })
                .buttonStyle(.plain)
                .help("Search for '\(svo.object)' in library")
            }
            .padding(.vertical, 4)
        } else if let excerpt = cleanedDisplayText(claim.sourceExcerpt) {
            // SVO missing → surface the verbatim source excerpt as the
            // card body so it isn't content-empty. The "regenerate KG"
            // hint moves to a small footer line so the user still
            // knows the SVO is absent. (#1006)
            VStack(alignment: .leading, spacing: 4) {
                Text(excerpt)
                    .font(.caption)
                    .lineLimit(isExpanded ? nil : 3)
                    .foregroundStyle(.primary)
                HStack(spacing: 4) {
                    Image(systemName: "questionmark.circle")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                    Text("No subject-verb-object — regenerate KG?")
                        .font(.caption2)
                        .foregroundStyle(.tertiary)
                        .italic()
                }
            }
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

}
