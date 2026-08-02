import SwiftUI

// MARK: - Checklists, Sources, Notes & the shared composer
// Split out of ResearchTasksPane+Views.swift, which reached the 400-line file
// limit when the pane's controls were given accessibility labels (#4484).
// Labelling is additive, so a file sitting at the limit forces the choice
// between an unannounced control and a baselined warning -- both of which let
// a style rule decide whether the pane is usable with VoiceOver.
//
// Every member here is `internal`, NOT `private`: `private` is file-scoped in
// Swift, so the moment a type spans two files every `private` member either
// side of the seam becomes invisible to the other. That is what broke the
// build on the last two splits of this shape.

extension ResearchTasksPane {

    // MARK: - Checklists tab

    @ViewBuilder
    var checklistsTab: some View {
        VStack(spacing: 0) {
            if researchStore.checklists.isEmpty {
                ContentUnavailableView(
                    "No Checklists",
                    systemImage: "checklist.checked",
                    description: Text("Add a verification checklist below.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                ScrollView {
                    LazyVStack(alignment: .leading, spacing: 8) {
                        ForEach(researchStore.checklists) { checklist in
                            checklistCard(checklist)
                        }
                    }
                    .padding(8)
                }
            }
            composer(placeholder: "New checklist…", text: $newChecklistText) { submitChecklist() }
        }
    }

    func checklistCard(_ checklist: ResearchChecklist) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(checklist.title).font(.headline)
            ForEach(checklist.items) { item in
                Button {
                    Task { await researchStore.toggleChecklistItem(checklist: checklist, item: item) }
                } label: {
                    HStack(spacing: 8) {
                        Image(systemName: item.checked ? "checkmark.square.fill" : "square")
                            .foregroundStyle(item.checked ? .green : .secondary)
                        Text(item.label).font(.body)
                        Spacer()
                    }
                }
                .buttonStyle(.plain)
            }
        }
        .padding(8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(Color(platformColor: .controlBackgroundColor))
        .clipShape(RoundedRectangle(cornerRadius: 6))
    }

    // MARK: - Sources tab

    @ViewBuilder
    var sourcesTab: some View {
        VStack(spacing: 0) {
            if researchStore.sources.isEmpty {
                ContentUnavailableView(
                    "No Sources",
                    systemImage: "link",
                    description: Text("Curate search sources for this project.")
                )
                .frame(maxWidth: .infinity, maxHeight: .infinity)
            } else {
                List(researchStore.sources) { source in
                    VStack(alignment: .leading, spacing: 2) {
                        Text(source.label).font(.body)
                        if let url = source.url, !url.isEmpty {
                            Text(url).font(.caption).foregroundStyle(.secondary).lineLimit(1)
                        }
                    }
                }
                .listStyle(.plain)
            }
            composer(placeholder: "Add source URL…", text: $newSourceText) { submitSource() }
        }
    }

    // MARK: - Notes tab

    var notesTab: some View {
        VStack(spacing: 0) {
            ScrollView {
                LazyVStack(alignment: .leading, spacing: 8) {
                    ForEach(researchStore.notes) { note in
                        noteCard(note)
                    }
                }
                .padding(8)
            }

            Divider()

            composer(placeholder: "Add a note…", text: $newNoteText) { submitNote() }
        }
    }

    @ViewBuilder
    func noteCard(_ note: ResearchNote) -> some View {
        if editingNoteId == note.id {
            VStack(alignment: .leading, spacing: 6) {
                TextField("Edit note…", text: $editingNoteText, axis: .vertical)
                    .textFieldStyle(.roundedBorder)
                    .lineLimit(2...6)
                HStack {
                    Button("Cancel") { editingNoteId = nil }
                    Spacer()
                    Button("Save") { Task { await saveNoteEdit(note) } }
                        .keyboardShortcut(.defaultAction)
                }
            }
            .padding(8)
            .background(Color(platformColor: .controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 6))
        } else {
            VStack(alignment: .leading, spacing: 4) {
                Text(note.content)
                    .font(.body)
                Text(note.createdAt, style: .relative)
                    .font(.caption2)
                    .foregroundStyle(.secondary)
            }
            .padding(8)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(Color(platformColor: .controlBackgroundColor))
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .onTapGesture { beginEditing(note) }
        }
    }

    // MARK: - Shared composer

    func composer(
        placeholder: String, text: Binding<String>, onSubmit: @escaping () -> Void
    ) -> some View {
        HStack(spacing: 8) {
            TextField(placeholder, text: text, axis: .vertical)
                .textFieldStyle(.plain)
                .lineLimit(1...3)
                .onSubmit(onSubmit)

            Button(action: onSubmit) {
                Image(systemName: "arrow.up.circle.fill")
                    .font(.title3)
            }
            .buttonStyle(.plain)
            .help("Submit")
            .accessibilityLabel("Submit")
            .disabled(text.wrappedValue.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
        }
        .padding(8)
    }
}
