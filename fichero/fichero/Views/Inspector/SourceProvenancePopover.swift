import SwiftUI

// MARK: - Claim attribution (#3448 shared model)

/// Who is asserting a claim. A claim's speaker is either the **document /
/// article itself** ("Article says XYZ about Z") or a **person in the archive**
/// ("Person P says XYZ about Z"), plus the verbatim quotation and where it sits
/// (#3448). Populated by the store from the engine's speaker fields (#3442);
/// declared here as a plain value type so both the provenance popover (#3449)
/// and the editable speaker surface (#3448) share one representation.
struct ClaimAttribution: Equatable {
    enum Kind: Equatable {
        case document
        case person
    }

    var kind: Kind
    /// Display name of the assertor — "the article" or the person's name.
    var name: String
    /// The verbatim span the assertion is drawn from, if known.
    var verbatimSpan: String?
    /// Human page/location label for the quotation, e.g. "p. 12".
    var locationLabel: String?

    var systemImage: String {
        switch kind {
        case .document: return "doc.text"
        case .person:   return "person"
        }
    }

    /// "Article says" / "Ada Lovelace says" — the lead-in shown above the span.
    var summary: String {
        "\(name) says"
    }
}

// MARK: - Provenance card (popover content)

/// The quick-look popover content for tracing any claim/entity/citation back to
/// its source (#3449 tier 1). Shows the attribution, the cropped source region
/// (reusing ``SourceSnippet``), the verbatim span, and a Reveal action that
/// drives the center Preview pane (tier 2). Cross-platform — plain SwiftUI.
struct SourceProvenanceCard: View {
    let request: ClaimSourceNavigationRequest
    var attribution: ClaimAttribution?
    /// Crop fetch seam (see ``SourceSnippet``); injected so the card stays
    /// context-agnostic and testable without the network.
    let fetch: SourceCropFetch
    /// Fired by "Reveal in Preview" — the host drives the Preview pane to the
    /// document/page and highlights the region (the source-nav contract, #2105).
    var onReveal: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            if let attribution {
                Label(attribution.summary, systemImage: attribution.systemImage)
                    .font(.caption.weight(.semibold))
                    .foregroundStyle(.secondary)
            }

            SourceSnippet(request: SourceCropRequest(request), fetch: fetch)

            if let span = verbatimSpan {
                Text("\u{201C}\(span)\u{201D}")
                    .font(.callout)
                    .italic()
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }

            if let location = attribution?.locationLabel ?? request.pageLabel.map({ "p. \($0)" }) {
                Text(location)
                    .font(.caption2)
                    .foregroundStyle(.tertiary)
            }

            Divider()

            Button(action: onReveal) {
                Label("Reveal in Preview", systemImage: "sidebar.right")
            }
            .buttonStyle(.borderless)
            .font(.callout)
        }
        .padding(12)
        // macOS popover wants a fixed width; on iPhone this popover adapts to a
        // sheet, where a hard 320pt clips on a 320pt device and can't shrink — so
        // cap instead of fix (#3666). The desktop popover is unchanged.
        #if os(macOS)
        .frame(width: 320)
        #else
        .frame(maxWidth: 320)
        #endif
    }

    /// Prefer the attribution's verbatim quotation; fall back to the claim text.
    private var verbatimSpan: String? {
        let candidate = attribution?.verbatimSpan ?? request.claimText
        guard let candidate, !candidate.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        else { return nil }
        return candidate
    }
}

// MARK: - Source chip (the row affordance)

/// The compact "source" affordance shown on a claim/entity/citation row.
/// Tapping opens the ``SourceProvenanceCard`` in a popover (a sheet on compact
/// iOS by default) — a glance at the evidence with no navigation. The same
/// `onReveal` seam drives the full reveal-in-Preview.
struct SourceProvenanceChip: View {
    let request: ClaimSourceNavigationRequest
    var attribution: ClaimAttribution?
    let fetch: SourceCropFetch
    var onReveal: () -> Void

    @State private var isPresented = false

    var body: some View {
        Button {
            isPresented = true
        } label: {
            Label(chipLabel, systemImage: "doc.text.magnifyingglass")
                .font(.caption)
                .labelStyle(.titleAndIcon)
        }
        .buttonStyle(.plain)
        .foregroundStyle(.secondary)
        .help("Show the source region for this record")
        .popover(isPresented: $isPresented) {
            SourceProvenanceCard(
                request: request,
                attribution: attribution,
                fetch: fetch,
                onReveal: {
                    isPresented = false
                    onReveal()
                }
            )
        }
    }

    private var chipLabel: String {
        if let page = request.pageLabel { return "p. \(page)" }
        return "Source"
    }
}
