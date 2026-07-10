import FicheroAPIClient
import SwiftUI

struct AnnotationUpdateActionParams: Encodable {
    let annotationId: String
    let update: Components.Schemas.AnnotationPatchRequest

    enum CodingKeys: String, CodingKey {
        case annotationId = "annotation_id"
        case update
    }
}

struct AnnotationDeleteActionParams: Encodable {
    let annotationId: String

    enum CodingKeys: String, CodingKey {
        case annotationId = "annotation_id"
    }
}

struct AnnotationPromoteActionParams: Encodable {
    let annotationId: String

    enum CodingKeys: String, CodingKey {
        case annotationId = "annotation_id"
    }
}

/// The shared renderer for one annotation.
///
/// Reuses the existing row-style presentation, then layers the edit / delete /
/// promote actions underneath. The detached window passes `nil` closures, so it
/// renders read-only.
struct AnnotationDetailView: View {
    let annotation: DocumentAnnotation?

    var onSave: ((DocumentAnnotation, String) async throws -> Void)?
    var onDelete: ((DocumentAnnotation) async throws -> Void)?
    var onPromote: ((DocumentAnnotation) async throws -> Void)?
    var onCopyCrop: ((DocumentAnnotation) async -> Void)?
    var onReveal: ((DocumentAnnotation) -> Void)?

    @State private var draftText = ""
    @State private var draftAnnotationId: String?
    @State private var isSaving = false
    @State private var errorText: String?

    var body: some View {
        Group {
            if let annotation {
                ScrollView {
                    VStack(alignment: .leading, spacing: 12) {
                        if let errorText {
                            errorBox(errorText)
                        }
                        AnnotationRow(annotation: annotation)
                            .padding(.bottom, 4)

                        editorSection(for: annotation)
                        metadataSection(for: annotation)
                        actionsSection(for: annotation)
                    }
                    .padding(.horizontal, 12)
                    .padding(.vertical, 10)
                    .frame(maxWidth: .infinity, alignment: .topLeading)
                }
                .onAppear { syncDraft(for: annotation) }
                .onChange(of: annotation.id) { _, _ in syncDraft(for: annotation) }
            } else {
                emptyState
            }
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .topLeading)
    }

    @ViewBuilder
    private func editorSection(for annotation: DocumentAnnotation) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Content")
                .font(.subheadline.weight(.semibold))
            if onSave != nil {
                TextEditor(text: $draftText)
                    .font(.body)
                    .frame(minHeight: 160)
                    .overlay(
                        RoundedRectangle(cornerRadius: 6)
                            .stroke(Color.secondary.opacity(0.25), lineWidth: 1)
                    )
            } else {
                Text(annotation.text?.isEmpty == false ? annotation.text ?? "" : "No annotation text")
                    .font(.body)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
        }
    }

    @ViewBuilder
    private func metadataSection(for annotation: DocumentAnnotation) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Metadata")
                .font(.subheadline.weight(.semibold))
            FlowMetadataChips(annotation: annotation)
            if let createdAt = annotation.createdAt, !createdAt.isEmpty {
                Text("Created \(createdAt)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
            if let updatedAt = annotation.updatedAt, !updatedAt.isEmpty {
                Text("Updated \(updatedAt)")
                    .font(.caption)
                    .foregroundStyle(.secondary)
            }
        }
    }

    @ViewBuilder
    private func actionsSection(for annotation: DocumentAnnotation) -> some View {
        if onSave != nil || onDelete != nil || onPromote != nil || onCopyCrop != nil || onReveal != nil {
            VStack(alignment: .leading, spacing: 8) {
                Text("Actions")
                    .font(.subheadline.weight(.semibold))
                primaryActions(for: annotation)
                saveDeleteActions(for: annotation)
            }
        }
    }

    @ViewBuilder
    private func primaryActions(for annotation: DocumentAnnotation) -> some View {
        HStack(spacing: 8) {
            if let onReveal, annotation.canRevealSource {
                Button("Reveal Source") { onReveal(annotation) }
            }
            if let onCopyCrop, annotation.canRevealSource && (annotation.hasRegion || annotation.hasSpan) {
                Button("Copy Cropped Content") {
                    Task { await onCopyCrop(annotation) }
                }
            }
            if let onPromote, annotation.canRevealSource {
                Button("Promote to Claim") {
                    Task {
                        await runMutation {
                            try await onPromote(annotation)
                        }
                    }
                }
                .buttonStyle(.bordered)
            }
            Spacer()
        }
    }

    @ViewBuilder
    private func saveDeleteActions(for annotation: DocumentAnnotation) -> some View {
        HStack {
            Spacer()
            if let onDelete {
                Button(role: .destructive) {
                    Task {
                        await runMutation {
                            try await onDelete(annotation)
                        }
                    }
                } label: {
                    Label("Delete", systemImage: "trash")
                }
            }
            if let onSave {
                Button {
                    Task {
                        await runMutation {
                            try await onSave(annotation, draftText)
                        }
                    }
                } label: {
                    if isSaving {
                        ProgressView().controlSize(.small)
                    } else {
                        Text("Save")
                    }
                }
                .buttonStyle(.borderedProminent)
                .disabled(draftText.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty || isSaving)
            }
        }
    }

    @ViewBuilder
    private var emptyState: some View {
        VStack(spacing: 8) {
            Image(systemName: "highlighter")
                .font(.title2)
                .foregroundStyle(.secondary)
            Text("No annotation selected")
                .font(.callout)
            Text("Pick an annotation from the list to see its details.")
                .font(.caption)
                .foregroundStyle(.secondary)
                .multilineTextAlignment(.center)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .padding(.vertical, 32)
    }

    @ViewBuilder
    private func errorBox(_ message: String) -> some View {
        HStack(alignment: .top, spacing: 6) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.orange)
            Text(message)
                .font(.caption)
                .foregroundStyle(.secondary)
            Spacer()
            Button("Dismiss") { errorText = nil }
                .buttonStyle(.bordered)
                .controlSize(.small)
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 8)
        .background(.orange.opacity(0.1))
    }

    private func syncDraft(for annotation: DocumentAnnotation) {
        if draftAnnotationId != annotation.id {
            draftAnnotationId = annotation.id
            draftText = annotation.text ?? ""
            errorText = nil
        }
    }

    private func runMutation(_ work: @escaping () async throws -> Void) async {
        isSaving = true
        errorText = nil
        do {
            try await work()
        } catch {
            errorText = error.localizedDescription
        }
        isSaving = false
    }
}

private struct FlowMetadataChips: View {
    let annotation: DocumentAnnotation

    var body: some View {
        FlowLayout(spacing: 6) {
            chip(annotation.kind.label)
            if let page = annotation.pageLabel, !page.isEmpty { chip("p. \(page)") }
            if annotation.hasRegion { chip("region") }
            if annotation.hasSpan { chip("span") }
            if !annotation.linkedClaimIds.isEmpty { chip("\(annotation.linkedClaimIds.count) claim") }
            if let rating = annotation.rating {
                chip(String(repeating: "*", count: max(0, min(5, rating))))
            }
            ForEach(Array(annotation.tags.prefix(4)), id: \.self) { tag in
                chip("#\(tag)")
            }
        }
    }

    private func chip(_ text: String) -> some View {
        Text(text)
            .font(.caption2)
            .padding(.horizontal, 6)
            .padding(.vertical, 2)
            .background(
                Capsule().fill(Color.accentColor.opacity(0.12))
            )
    }
}
