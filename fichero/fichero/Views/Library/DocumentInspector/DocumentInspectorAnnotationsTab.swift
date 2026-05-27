import SwiftUI

extension Notification.Name {
    /// Posted when the user taps an annotation row in the inspector's Annotations
    /// tab. The reading surface (PDF / image viewer) can observe this to scroll to
    /// the source page and, if a `bbox` is present, highlight the region (#1276).
    /// userInfo keys: documentId, pageLabel?, bbox?([Double]), charStart?, charEnd?.
    static let annotationSelectedInInspector = Notification.Name("annotationSelectedInInspector")
}

/// Annotations tab for the Document Inspector (#1276).
///
/// Lists a document's annotations, lets the user add a quick note and delete any
/// annotation, and reveals an annotation's source page/region on tap. Wired to
/// `AnnotationService` (backend `/api/annotations`); degrades to an empty state
/// if the backend route isn't reachable yet (parallel development).
struct DocumentInspectorAnnotationsTab: View {
    let document: Document

    @StateObject private var service = AnnotationService()
    @State private var newNoteText: String = ""
    @State private var isAdding = false
    @FocusState private var noteFieldFocused: Bool

    var body: some View {
        VStack(spacing: 0) {
            addBar
            Divider()
            content
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .task(id: document.id) {
            await service.load(documentId: document.id)
        }
        .accessibilityIdentifier("annotationsTab")
    }

    // MARK: - Add bar

    private var addBar: some View {
        HStack(spacing: 8) {
            Image(systemName: "note.text.badge.plus")
                .foregroundStyle(.secondary)
            TextField("Add a note…", text: $newNoteText)
                .textFieldStyle(.plain)
                .focused($noteFieldFocused)
                .onSubmit { addNote() }
                .accessibilityIdentifier("annotationNoteField")
            Button {
                addNote()
            } label: {
                if isAdding {
                    ProgressView().controlSize(.small)
                } else {
                    Text("Add")
                }
            }
            .buttonStyle(.borderedProminent)
            .controlSize(.small)
            .disabled(newNoteText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isAdding)
            .accessibilityIdentifier("annotationAddButton")
        }
        .padding(.horizontal, 12)
        .frame(height: 44)
    }

    // MARK: - Content

    @ViewBuilder
    private var content: some View {
        if service.isLoading && service.annotations.isEmpty {
            ProgressView("Loading annotations…")
                .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if service.annotations.isEmpty {
            emptyState
        } else {
            List {
                ForEach(service.annotations) { annotation in
                    AnnotationRow(annotation: annotation) {
                        reveal(annotation)
                    }
                    .contextMenu {
                        Button(role: .destructive) {
                            delete(annotation)
                        } label: {
                            Label("Delete Annotation", systemImage: "trash")
                        }
                    }
                }
            }
            .listStyle(.inset)
        }
    }

    private var emptyState: some View {
        VStack(spacing: 12) {
            Image(systemName: "highlighter")
                .font(.system(size: 32))
                .foregroundStyle(.secondary)
            Text("No annotations")
                .font(.headline)
            Text(service.error ?? "Add a note above, or highlight a region on the page.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .padding()
    }

    // MARK: - Actions

    private func addNote() {
        let trimmed = newNoteText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty, !isAdding else { return }
        isAdding = true
        Task {
            let created = await service.addNote(documentId: document.id, text: trimmed)
            if created != nil { newNoteText = "" }
            isAdding = false
            noteFieldFocused = false
        }
    }

    private func delete(_ annotation: DocumentAnnotation) {
        Task { await service.delete(id: annotation.id) }
    }

    /// Reveal the annotation's source page/region by posting a notification the
    /// reading surface can observe. Decoupled so the inspector doesn't need a
    /// direct reference to the viewer (#1276).
    private func reveal(_ annotation: DocumentAnnotation) {
        var info: [String: Any] = ["documentId": annotation.documentId]
        if let pageLabel = annotation.pageLabel { info["pageLabel"] = pageLabel }
        if let bbox = annotation.bbox { info["bbox"] = bbox }
        if let charStart = annotation.charStart { info["charStart"] = charStart }
        if let charEnd = annotation.charEnd { info["charEnd"] = charEnd }
        NotificationCenter.default.post(
            name: .annotationSelectedInInspector,
            object: nil,
            userInfo: info
        )
    }
}

// MARK: - Row

/// A single annotation row: kind icon, note text, and a metadata caption
/// (page / region / rating / tags).
private struct AnnotationRow: View {
    let annotation: DocumentAnnotation
    let onTap: () -> Void

    var body: some View {
        Button(action: onTap) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: annotation.kind.icon)
                    .foregroundStyle(.secondary)
                    .frame(width: 18)
                VStack(alignment: .leading, spacing: 3) {
                    Text(displayText)
                        .font(.body)
                        .foregroundStyle(annotation.text?.isEmpty == false ? .primary : .secondary)
                        .lineLimit(3)
                        .multilineTextAlignment(.leading)
                    if !metadataParts.isEmpty {
                        Text(metadataParts.joined(separator: " · "))
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }
                Spacer(minLength: 0)
                if annotation.hasRegion || annotation.hasSpan {
                    Image(systemName: "arrow.right.circle")
                        .foregroundStyle(.tertiary)
                        .help("Reveal source")
                }
            }
            .contentShape(Rectangle())
            .padding(.vertical, 2)
        }
        .buttonStyle(.plain)
    }

    private var displayText: String {
        if let text = annotation.text, !text.isEmpty { return text }
        return "(\(annotation.kind.label.lowercased()) — no text)"
    }

    private var metadataParts: [String] {
        var parts: [String] = [annotation.kind.label]
        if let page = annotation.pageLabel, !page.isEmpty { parts.append("p. \(page)") }
        if annotation.hasRegion { parts.append("region") }
        if let rating = annotation.rating { parts.append(String(repeating: "★", count: max(0, min(5, rating)))) }
        for tag in annotation.tags.prefix(3) { parts.append("#\(tag)") }
        return parts
    }
}
