import FicheroAPIClient
import SwiftUI

extension Notification.Name {
    /// Posted when the user selects an annotation in the inspector.
    static let annotationSelectedInInspector = Notification.Name("annotationSelectedInInspector")
}

/// A native `List(selection:)` of annotations.
///
/// Keeps the rows lightweight: type icon, body preview, and a compact metadata
/// line. Selecting a row updates the shared `FocusedAnnotation`, which the
/// detail view and detached window both observe.
struct AnnotationListView: View {
    let annotations: [DocumentAnnotation]

    @Bindable var focused: FocusedAnnotation

    var onOpenInWindow: (() -> Void)?

    private var sortedAnnotations: [DocumentAnnotation] {
        annotations.sorted { lhs, rhs in
            let lhsDate = lhs.updatedAt ?? lhs.createdAt ?? ""
            let rhsDate = rhs.updatedAt ?? rhs.createdAt ?? ""
            return lhsDate > rhsDate
        }
    }

    var body: some View {
        List(selection: $focused.id) {
            ForEach(sortedAnnotations) { annotation in
                row(for: annotation)
                    .tag(annotation.id)
                    .contextMenu {
                        if let onOpenInWindow {
                            Button("Open in Window") {
                                focused.select(annotation.id, in: annotations)
                                onOpenInWindow()
                            }
                        }
                    }
            }
        }
        .listStyle(.inset)
        .overlay {
            if annotations.isEmpty {
                emptyState
            }
        }
        .onChange(of: focused.id) { _, newId in
            guard let newId else {
                focused.clear()
                return
            }
            focused.resolve(in: annotations)
            guard let annotation = annotations.first(where: { $0.id == newId }) else { return }
            postRevealNotification(for: annotation)
        }
        .onChange(of: annotations) { _, items in
            focused.resolve(in: items)
        }
    }

    @ViewBuilder
    private func row(for annotation: DocumentAnnotation) -> some View {
        AnnotationRow(annotation: annotation)
    }

    private var emptyState: some View {
        // Standardized on ContentUnavailableView (#3039) — system semantic fonts,
        // consistent with every other lens/inspector empty state.
        ContentUnavailableView(
            "No annotations",
            systemImage: "highlighter",
            description: Text("Add a note, or highlight a region on the page.")
        )
    }

    private func postRevealNotification(for annotation: DocumentAnnotation) {
        guard let documentId = annotation.documentId else { return }
        var info: [String: Any] = ["documentId": documentId]
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

/// A single annotation row: kind icon, note text, and compact metadata.
struct AnnotationRow: View {
    let annotation: DocumentAnnotation
    @Environment(\.appearsActive) private var appearsActive

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: annotation.kind.icon)
                .foregroundStyle(appearsActive ? .secondary : .tertiary)
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
            if annotation.canRevealSource && (annotation.hasRegion || annotation.hasSpan) {
                Image(systemName: "arrow.right.circle")
                    .foregroundStyle(appearsActive ? .tertiary : .quaternary)
                    .help("Reveal source")
            }
        }
        .padding(.vertical, 2)
        .contentShape(Rectangle())
    }

    private var displayText: String {
        if let text = annotation.text, !text.isEmpty { return text }
        return "(\(annotation.kind.label.lowercased()) — no text)"
    }

    private var metadataParts: [String] {
        var parts: [String] = [annotation.kind.label]
        if let page = annotation.pageLabel, !page.isEmpty { parts.append("p. \(page)") }
        if annotation.hasRegion { parts.append("region") }
        if !annotation.linkedClaimIds.isEmpty { parts.append("\(annotation.linkedClaimIds.count) claim") }
        if let rating = annotation.rating { parts.append(String(repeating: "*", count: max(0, min(5, rating)))) }
        for tag in annotation.tags.prefix(3) { parts.append("#\(tag)") }
        return parts
    }
}
