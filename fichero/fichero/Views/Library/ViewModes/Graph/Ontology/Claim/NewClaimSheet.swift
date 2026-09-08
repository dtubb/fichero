import FicheroAPIClient
import SwiftUI

// MARK: - New Claim Sheet (kg-tables `claim.create`)

/// Hand-author a KnowledgeClaim — the claim analogue of `NewEntitySheet`. A
/// researcher asserts a claim in their own words ("Matheo del Mazo vende cargas de
/// ropa"); subject/verb/object are parsed server-side. Backed by
/// `EntityService.createClaim` (POST /api/claims). The service is passed in
/// explicitly (not read from the environment) so the write always lands in the
/// library the table is showing — the same wrong-library hazard `NewEntitySheet`
/// warns about (#4306/#4461).
///
/// A manual claim MAY have no source document — a working hypothesis / synthesis —
/// and the form says so plainly, so a sourceless claim is never silently
/// indistinguishable from a sourced one (spec: claim.create.source-optional-flagged).
struct NewClaimSheet: View {
    let entityService: EntityService
    /// Optional source document for the claim (the folder/page in view). `nil`
    /// makes a sourceless working hypothesis.
    var sourceDocumentId: String?
    var onCreated: (Components.Schemas.KnowledgeClaim) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var text: String = ""
    @State private var isSaving = false
    @State private var errorText: String?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack {
                Text("New Claim").font(.headline)
                Spacer()
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
            }
            .padding()
            Divider()
            form
            Spacer()
            footer
        }
        #if os(macOS)
        .frame(width: 460, height: 300)
        #endif
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Claim")
                .font(.caption)
                .foregroundStyle(.secondary)
            TextEditor(text: $text)
                .frame(minHeight: 90)
                .border(Color.gray.opacity(0.2))
            Text("e.g. “Matheo del Mazo vende cargas de ropa”. Subject, verb and object are parsed for you.")
                .font(.caption)
                .foregroundStyle(.secondary)
            Label(
                sourceDocumentId == nil
                    ? "No source — this is a working hypothesis, marked lower-provenance."
                    : "Source: the folder or page in view.",
                systemImage: sourceDocumentId == nil ? "questionmark.circle" : "doc.text"
            )
            .font(.caption)
            .foregroundStyle(.secondary)
        }
        .padding()
    }

    private var footer: some View {
        HStack {
            if let errorText {
                Text(errorText).font(.caption).foregroundStyle(.red).lineLimit(2)
            }
            Spacer()
            Button("Create", action: save)
                .keyboardShortcut(.defaultAction)
                .buttonStyle(.borderedProminent)
                .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving)
        }
        .padding()
    }

    private func save() {
        let claimText = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !claimText.isEmpty else { return }
        isSaving = true
        errorText = nil
        Task {
            do {
                let claim = try await entityService.createClaim(
                    text: claimText,
                    sourceDocumentId: sourceDocumentId
                )
                onCreated(claim)
                dismiss()
            } catch {
                errorText = error.localizedDescription
            }
            isSaving = false
        }
    }
}
