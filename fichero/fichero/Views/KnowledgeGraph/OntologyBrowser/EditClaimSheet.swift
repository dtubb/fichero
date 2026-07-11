import FicheroAPIClient
import SwiftUI

private struct ClaimPatchActionParams: Encodable {
    let claimId: String
    let patch: Components.Schemas.ClaimPatchRequest

    enum CodingKeys: String, CodingKey {
        case claimId = "claim_id"
        case patch
    }
}

/// Sheet for editing the text, type, and epistemic status of a claim (#1135).
/// Calls PATCH /api/claims/{id} on save.
struct EditClaimSheet: View {
    let claim: Components.Schemas.KnowledgeClaim
    let onSave: (Components.Schemas.KnowledgeClaim) -> Void

    @Environment(\.dismiss) private var dismiss
    @Environment(WindowState.self) private var windowState
    @State private var text: String
    @State private var subject: String
    @State private var predicate: String
    @State private var object: String
    @State private var sourcePageLabel: String
    @State private var claimType: String
    @State private var epistemicStatus: String
    @State private var isSaving = false
    @State private var errorText: String?

    static let claimTypeOptions: [(label: String, raw: String)] = [
        ("Fact", "fact"),
        ("Claim", "claim"),
        ("Quotation", "quotation"),
        ("Hypothesis", "hypothesis"),
        ("Definition", "definition"),
        ("Judgment", "judgment"),
        ("Method", "method")
    ]

    static let epistemicStatusOptions: [(label: String, raw: String)] = [
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
        _subject = State(initialValue: claim.subjectCanonical ?? "")
        _predicate = State(initialValue: claim.predicateVerb ?? "")
        _object = State(initialValue: claim.objectPhrase ?? "")
        _sourcePageLabel = State(initialValue: claim.sourcePageLabel ?? "")
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

                Section("Subject-Verb-Object") {
                    TextField("Subject", text: $subject)
                    TextField("Predicate", text: $predicate)
                    TextField("Object", text: $object)
                    TextField("Source page", text: $sourcePageLabel)
                }

                Section("Review") {
                    Picker("Kind", selection: $claimType) {
                        ForEach(Self.claimTypeOptions, id: \.raw) { item in
                            Text(item.label).tag(item.raw)
                        }
                    }
                    Picker("Epistemic Status", selection: $epistemicStatus) {
                        ForEach(Self.epistemicStatusOptions, id: \.raw) { item in
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
        .frame(width: 520, height: 520)
    }

    private func save() {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.getLibrary(id: windowState.libraryId) else { return }
        isSaving = true
        errorText = nil
        Task {
            do {
                let typeEnum = Components.Schemas.ClaimType(rawValue: claimType)
                let statusEnum = Components.Schemas.EpistemicStatus(rawValue: epistemicStatus)
                var patch = Components.Schemas.ClaimPatchRequest()
                patch.text = text.trimmingCharacters(in: .whitespacesAndNewlines)
                patch.subjectCanonical = trimmedOrNil(subject)
                patch.predicateVerb = trimmedOrNil(predicate)
                patch.objectPhrase = trimmedOrNil(object)
                patch.sourcePageLabel = trimmedOrNil(sourcePageLabel)
                patch.claimType = typeEnum
                patch.epistemicStatus = statusEnum
                _ = try await library.actionsService.invokeAction(
                    name: "claim.patch",
                    params: ClaimPatchActionParams(claimId: claimId, patch: patch)
                )
                dismiss()
            } catch {
                errorText = error.localizedDescription
                isSaving = false
            }
        }
    }

    private func trimmedOrNil(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}

struct InlineClaimEditor: View {
    let claim: Components.Schemas.KnowledgeClaim
    let onCancel: () -> Void
    let onSave: (Components.Schemas.KnowledgeClaim) -> Void

    @Environment(WindowState.self) private var windowState
    @State private var subject: String
    @State private var predicate: String
    @State private var object: String
    @State private var sourcePageLabel: String
    @State private var claimType: String
    @State private var epistemicStatus: String
    @State private var isSaving = false
    @State private var errorText: String?

    init(
        claim: Components.Schemas.KnowledgeClaim,
        onCancel: @escaping () -> Void,
        onSave: @escaping (Components.Schemas.KnowledgeClaim) -> Void
    ) {
        self.claim = claim
        self.onCancel = onCancel
        self.onSave = onSave
        _subject = State(initialValue: claim.subjectCanonical ?? "")
        _predicate = State(initialValue: claim.predicateVerb ?? "")
        _object = State(initialValue: claim.objectPhrase ?? "")
        _sourcePageLabel = State(initialValue: claim.sourcePageLabel ?? "")
        _claimType = State(initialValue: claim.claimType?.rawValue ?? "claim")
        _epistemicStatus = State(initialValue: claim.epistemicStatus?.rawValue ?? "tentative")
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                TextField("Subject", text: $subject)
                TextField("Predicate", text: $predicate)
                TextField("Object", text: $object)
            }
            HStack(spacing: 6) {
                Picker("Kind", selection: $claimType) {
                    ForEach(EditClaimSheet.claimTypeOptions, id: \.raw) { item in
                        Text(item.label).tag(item.raw)
                    }
                }
                Picker("Status", selection: $epistemicStatus) {
                    ForEach(EditClaimSheet.epistemicStatusOptions, id: \.raw) { item in
                        Text(item.label).tag(item.raw)
                    }
                }
                TextField("Page", text: $sourcePageLabel)
                    .frame(width: 80)
            }
            if let errorText {
                Text(errorText)
                    .font(.caption)
                    .foregroundStyle(.red)
            }
            HStack {
                Spacer()
                Button("Cancel", action: onCancel)
                Button("Save", action: save)
                    .buttonStyle(.borderedProminent)
                    .disabled(isSaving)
            }
        }
        .padding(10)
        .background(Color(.windowBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    private func save() {
        guard let claimId = claim.id,
              let library = LibraryManager.shared.getLibrary(id: windowState.libraryId) else { return }
        isSaving = true
        errorText = nil
        Task {
            do {
                var patch = Components.Schemas.ClaimPatchRequest()
                patch.subjectCanonical = trimmedOrNil(subject)
                patch.predicateVerb = trimmedOrNil(predicate)
                patch.objectPhrase = trimmedOrNil(object)
                patch.sourcePageLabel = trimmedOrNil(sourcePageLabel)
                patch.claimType = Components.Schemas.ClaimType(rawValue: claimType)
                patch.epistemicStatus = Components.Schemas.EpistemicStatus(rawValue: epistemicStatus)
                _ = try await library.actionsService.invokeAction(
                    name: "claim.patch",
                    params: ClaimPatchActionParams(claimId: claimId, patch: patch)
                )
                onSave(claim)
            } catch {
                errorText = error.localizedDescription
                isSaving = false
            }
        }
    }

    private func trimmedOrNil(_ value: String) -> String? {
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
