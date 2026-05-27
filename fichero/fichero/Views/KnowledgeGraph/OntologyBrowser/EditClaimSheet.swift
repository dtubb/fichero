import FicheroAPIClient
import SwiftUI

/// Sheet for editing the text, type, and epistemic status of a claim (#1135).
/// Calls PATCH /api/claims/{id} on save.
struct EditClaimSheet: View {
    let claim: Components.Schemas.KnowledgeClaim
    let onSave: (Components.Schemas.KnowledgeClaim) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var text: String
    @State private var claimType: String
    @State private var epistemicStatus: String
    @State private var isSaving = false
    @State private var errorText: String?

    private static let claimTypes: [(label: String, raw: String)] = [
        ("Fact", "fact"),
        ("Claim", "claim"),
        ("Quotation", "quotation"),
        ("Hypothesis", "hypothesis"),
        ("Definition", "definition"),
        ("Judgment", "judgment"),
        ("Method", "method")
    ]

    private static let epistemicStatuses: [(label: String, raw: String)] = [
        ("Confirmed", "confirmed"),
        ("Tentative", "tentative"),
        ("Rejected", "rejected")
    ]

    init(
        claim: Components.Schemas.KnowledgeClaim,
        onSave: @escaping (Components.Schemas.KnowledgeClaim) -> Void
    ) {
        self.claim = claim
        self.onSave = onSave
        _text = State(initialValue: claim.text)
        _claimType = State(initialValue: claim.claimType?.rawValue ?? "claim")
        _epistemicStatus = State(initialValue: claim.epistemicStatus?.rawValue ?? "tentative")
    }

    var body: some View {
        VStack(spacing: 0) {
            Form {
                Section("Claim Text") {
                    TextEditor(text: $text)
                        .font(.body)
                        .frame(minHeight: 80)
                }

                Section("Classification") {
                    Picker("Type", selection: $claimType) {
                        ForEach(Self.claimTypes, id: \.raw) { item in
                            Text(item.label).tag(item.raw)
                        }
                    }
                    Picker("Epistemic Status", selection: $epistemicStatus) {
                        ForEach(Self.epistemicStatuses, id: \.raw) { item in
                            Text(item.label).tag(item.raw)
                        }
                    }
                }

                if let errorText {
                    Section {
                        Text(errorText)
                            .foregroundStyle(.red)
                            .font(.caption)
                    }
                }
            }
            .formStyle(.grouped)

            Divider()

            HStack {
                Button("Cancel") { dismiss() }
                    .keyboardShortcut(.cancelAction)
                Spacer()
                Button("Save", action: save)
                    .keyboardShortcut(.defaultAction)
                    .disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving)
            }
            .padding()
        }
        .frame(width: 480, height: 340)
    }

    private func save() {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.globalLibrary else { return }
        isSaving = true
        errorText = nil
        Task {
            do {
                let typeEnum = Components.Schemas.ClaimType(rawValue: claimType)
                let statusEnum = Components.Schemas.EpistemicStatus(rawValue: epistemicStatus)
                let updated = try await library.entityService.patchClaim(
                    claimId,
                    text: text.trimmingCharacters(in: .whitespacesAndNewlines),
                    claimType: typeEnum,
                    epistemicStatus: statusEnum
                )
                onSave(updated)
                dismiss()
            } catch {
                errorText = error.localizedDescription
                isSaving = false
            }
        }
    }
}
