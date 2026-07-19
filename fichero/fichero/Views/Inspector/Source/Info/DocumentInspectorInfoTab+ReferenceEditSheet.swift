import FicheroAPIClient
import SwiftUI

// MARK: - ReferenceEditSheet (#3258)

/// Native Form sheet to edit a reference's core metadata, saved via the
/// undoable PATCH. Inline validation: title required, year must be blank or a
/// plausible integer. Authors are edited as a comma-separated list.
struct ReferenceEditSheet: View {
    let reference: Components.Schemas.Reference
    /// Async save; throwing surfaces an inline error and keeps the sheet open.
    let onSave: @MainActor ([String: Any]) async throws -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var title: String
    @State private var authors: String
    @State private var yearText: String
    @State private var doi: String
    @State private var journal: String
    @State private var isSaving = false
    @State private var saveError: String?

    init(
        reference: Components.Schemas.Reference,
        onSave: @escaping @MainActor ([String: Any]) async throws -> Void
    ) {
        self.reference = reference
        self.onSave = onSave
        _title = State(initialValue: reference.title ?? "")
        _authors = State(initialValue: (reference.authors ?? []).joined(separator: ", "))
        _yearText = State(initialValue: reference.year.map(String.init) ?? "")
        _doi = State(initialValue: reference.doi ?? "")
        _journal = State(initialValue: reference.journalOrBook ?? "")
    }

    private var yearIsValid: Bool {
        let trimmed = yearText.trimmingCharacters(in: .whitespaces)
        if trimmed.isEmpty { return true }
        guard let year = Int(trimmed), year > 0, year < 3000 else { return false }
        return true
    }

    private var canSave: Bool {
        !isSaving && yearIsValid && !title.trimmingCharacters(in: .whitespaces).isEmpty
    }

    var body: some View {
        NavigationStack {
            Form {
                Section("Reference") {
                    TextField("Title", text: $title, axis: .vertical)
                    TextField("Authors (comma-separated)", text: $authors, axis: .vertical)
                    TextField("Year", text: $yearText)
                        .foregroundStyle(yearIsValid ? Color.primary : Color.red)
                    TextField("Journal or book", text: $journal)
                    TextField("DOI", text: $doi)
                }
                if !yearIsValid {
                    Text("Year must be a number (or left blank).")
                        .font(.caption)
                        .foregroundStyle(.red)
                }
                if let saveError {
                    Text(saveError)
                        .font(.caption)
                        .foregroundStyle(.red)
                }
            }
            .formStyle(.grouped)
            .navigationTitle("Edit Reference")
            .toolbar {
                ToolbarItem(placement: .cancellationAction) {
                    Button("Cancel") { dismiss() }
                }
                ToolbarItem(placement: .confirmationAction) {
                    Button("Save") { save() }
                        .disabled(!canSave)
                }
            }
        }
        .frame(minWidth: 380, minHeight: 320)
    }

    private func save() {
        isSaving = true
        Task { @MainActor in
            defer { isSaving = false }
            do {
                try await onSave(buildPatch())
                dismiss()
            } catch {
                saveError = error.localizedDescription
            }
        }
    }

    /// Snake-case patch matching the backend Reference fields. Empty text clears
    /// the string field; a blank year is omitted (not cleared).
    private func buildPatch() -> [String: Any] {
        let parsedAuthors = authors
            .split(separator: ",")
            .map { $0.trimmingCharacters(in: .whitespaces) }
            .filter { !$0.isEmpty }
        var patch: [String: Any] = [
            "title": title.trimmingCharacters(in: .whitespaces),
            "authors": parsedAuthors,
            "journal_or_book": journal.trimmingCharacters(in: .whitespaces),
            "doi": doi.trimmingCharacters(in: .whitespaces)
        ]
        if let year = Int(yearText.trimmingCharacters(in: .whitespaces)) {
            patch["year"] = year
        }
        return patch
    }
}
