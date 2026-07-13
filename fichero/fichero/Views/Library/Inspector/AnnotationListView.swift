import FicheroAPIClient
import SwiftUI

/// Maps an annotation to the shared typed source-navigation request (#3432),
/// replacing the unconsumed `annotationSelectedInInspector` NotificationCenter
/// bus. Pure + testable: resolves document id, page label, bbox, and character
/// range into the `ClaimSourceNavigationRequest` that ContentView/the reader
/// already consume. Returns nil when there's no document anchor to navigate to.
enum AnnotationSourceNavigation {
    static func request(for annotation: DocumentAnnotation) -> ClaimSourceNavigationRequest? {
        guard let documentId = annotation.documentId,
              !documentId.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else {
            return nil
        }
        return ClaimSourceNavigationRequest(
            documentId: documentId,
            pageLabel: annotation.pageLabel,
            charStart: annotation.charStart,
            charEnd: annotation.charEnd,
            bbox: annotation.bbox
        )
    }
}

/// A native `List(selection:)` of annotations.
///
/// Keeps the rows lightweight: type icon, body preview, and a compact metadata
/// line. Selecting a row updates the shared `FocusedAnnotation`, which the
/// detail view and detached window both observe.
struct AnnotationListView: View {
    let annotations: [DocumentAnnotation]

    @Bindable var focused: FocusedAnnotation

    /// Per-window typed source-navigation bus (#3437/#3432); optional so a host
    /// that hasn't injected it safely no-ops instead of posting into the void.
    @Environment(ClaimSourceNavigationState.self) private var claimSourceNavigationState: ClaimSourceNavigationState?

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
            navigateToSource(of: annotation)
        }
        .onChange(of: annotations) { _, items in
            focused.resolve(in: items)
        }
    }

    @ViewBuilder
    private func row(for annotation: DocumentAnnotation) -> some View {
        AnnotationRow(annotation: annotation)
            .draggable(LibraryItemDrag(
                kind: .annotation,
                id: annotation.id,
                documentId: annotation.documentId,
                text: annotation.text?.isEmpty == false ? annotation.text ?? annotation.kind.label : annotation.kind.label
            ))
            .inspectorListRowTarget()
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

    private func navigateToSource(of annotation: DocumentAnnotation) {
        guard let request = AnnotationSourceNavigation.request(for: annotation) else { return }
        claimSourceNavigationState?.request(request)
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
        .inspectorListRowTarget()
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
