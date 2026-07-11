import FicheroAPIClient
import SwiftUI

// MARK: - Map a claim to its attribution (#3448)

extension ClaimAttribution {
    /// Derive a claim's attribution from the engine's speaker fields (#1123).
    /// A claim asserted by a **person in the archive** carries a
    /// `speakerEntityId` or a free `speakerName`; otherwise the assertor is the
    /// **document/article itself**. `claimSpeaker` is the engine's formatted
    /// display string (e.g. "the article").
    init(claim: Components.Schemas.KnowledgeClaim) {
        let entityId = claim.speakerEntityId?.trimmingCharacters(in: .whitespacesAndNewlines)
        let speaker = claim.speakerName?.trimmingCharacters(in: .whitespacesAndNewlines)
        let hasEntity = !(entityId ?? "").isEmpty
        let hasName = !(speaker ?? "").isEmpty

        if hasEntity || hasName {
            self.init(
                kind: .person,
                name: speaker ?? claim.claimSpeaker ?? "Unknown speaker",
                verbatimSpan: claim.text,
                locationLabel: claim.sourcePageLabel.map { "p. \($0)" }
            )
        } else {
            self.init(
                kind: .document,
                name: claim.claimSpeaker ?? "This document",
                verbatimSpan: claim.text,
                locationLabel: claim.sourcePageLabel.map { "p. \($0)" }
            )
        }
    }
}

// MARK: - Attribution surface (display + edit)

/// Surfaces + edits a claim's speaker/attribution (#3448): who is asserting —
/// the document/article vs a person in the archive — with the verbatim span and
/// location. Editing sets the speaker *name* (attributes the claim to a person);
/// persistence flows through `ClaimStore.patch(speakerName:)`. Cross-platform.
///
/// The host injects the current attribution + an `onSetSpeaker` seam so this
/// view is context-agnostic and unit-testable without a store.
struct ClaimAttributionView: View {
    let attribution: ClaimAttribution
    /// Persist a new speaker name (→ person-asserted). `nil`/empty is ignored
    /// here — clearing back to document-asserted needs explicit-null patch
    /// support the engine doesn't yet expose (flagged on #3448).
    var onSetSpeaker: (String) async -> Void

    @State private var isEditing = false
    @State private var draftName = ""
    @State private var isSaving = false

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if isEditing {
                editor
            } else {
                display
            }
        }
    }

    private var display: some View {
        HStack(spacing: 6) {
            Label(attribution.summary, systemImage: attribution.systemImage)
                .font(.caption.weight(.semibold))
                .foregroundStyle(.secondary)
            Spacer(minLength: 4)
            Button {
                draftName = attribution.kind == .person ? attribution.name : ""
                isEditing = true
            } label: {
                Image(systemName: "pencil")
            }
            .buttonStyle(.borderless)
            .help("Attribute this claim to a person")
            .accessibilityLabel("Edit speaker")
        }
    }

    private var editor: some View {
        HStack(spacing: 6) {
            TextField("Speaker name", text: $draftName)
                .textFieldStyle(.roundedBorder)
                .onSubmit { Task { await save() } }
            Button("Save") { Task { await save() } }
                .disabled(isSaving || draftName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
            Button("Cancel") { isEditing = false }
                .buttonStyle(.borderless)
        }
        .font(.caption)
    }

    private func save() async {
        let name = draftName.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !name.isEmpty else { return }
        isSaving = true
        await onSetSpeaker(name)
        isSaving = false
        isEditing = false
    }
}
