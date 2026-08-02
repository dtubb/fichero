import FicheroAPIClient
import SwiftUI

// MARK: - ReferenceRowView (#3258)

/// A single bibliography row: title, authors/year/journal metadata, an
/// expandable BibTeX preview, and a context menu (edit / resolve / delete).
/// Referenced by `DocumentBibliographyPanel.referenceRow`.
struct ReferenceRowView: View {
    let ref: Components.Schemas.Reference
    let isSelf: Bool
    /// A DOI/ISBN resolve is in flight for this row (#3258).
    var isResolving = false
    /// Present only for editable rows (#3258); nil disables the edit action.
    var onEdit: (() -> Void)?
    /// Present only when the row has a DOI/ISBN to resolve (#3258).
    var onResolve: (() -> Void)?
    /// Present only for deletable rows (#3258); nil disables the delete action.
    var onDelete: (() -> Void)?

    @State private var isExpanded = false
    @State private var copied = false

    var body: some View {
        rowContent
            .contextMenu {
                if let onEdit {
                    Button("Edit…", systemImage: "pencil", action: onEdit)
                }
                if let onResolve {
                    Button("Resolve Metadata", systemImage: "sparkle.magnifyingglass", action: onResolve)
                        .disabled(isResolving)
                }
                if let onDelete {
                    Button("Delete Reference…", role: .destructive, action: onDelete)
                }
            }
    }

    private var rowContent: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 4) {
                if isSelf {
                    Image(systemName: "doc.text")
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                }
                Text(refTitle)
                    .font(.caption)
                    .foregroundStyle(.primary)
                    .lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                if isResolving {
                    ProgressView()
                        .scaleEffect(0.5)
                        .help("Resolving metadata…")
                }
                Spacer(minLength: 4)
                if let bibtex = ref.bibtex, !bibtex.isEmpty {
                    Button {
                        if isExpanded {
                            PlatformPasteboard.writeString(bibtex)
                            copied = true
                        } else {
                            isExpanded = true
                        }
                    } label: {
                        Image(systemName: copied ? "checkmark" : (isExpanded ? "doc.on.doc" : "chevron.down"))
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }
                    .buttonStyle(.plain)
                    .help(isExpanded ? "Copy BibTeX" : "Show BibTeX")
                    // #4479: VoiceOver announced nothing here. The button was
                    // invisible to check_accessibility because its trailing
                    // `.onChange { }` truncated the scan — a real gap the
                    // scanner's own blindness was hiding, not an allowlisted
                    // decision. Mirrors `.help`, and reports the COPIED state
                    // too, which the icon shows and the help does not.
                    .accessibilityLabel(
                        copied ? "BibTeX copied" : (isExpanded ? "Copy BibTeX" : "Show BibTeX")
                    )
                    .onChange(of: copied) { _, newValue in
                        if newValue {
                            Task {
                                try? await Task.sleep(for: .seconds(1.5))
                                copied = false
                            }
                        }
                    }
                }
            }
            HStack(spacing: 6) {
                if let authors = ref.authors, !authors.isEmpty {
                    Text(authors.prefix(2).joined(separator: ", "))
                        .font(.caption2)
                        .foregroundStyle(.secondary)
                        .lineLimit(1)
                }
                if let year = ref.year {
                    Text(String(year))
                        .font(.caption2.monospacedDigit())
                        .foregroundStyle(.tertiary)
                }
                if let doi = ref.doi, !doi.isEmpty {
                    Text("DOI")
                        .font(.caption2)
                        .foregroundStyle(Color.accentColor)
                        .help(doi)
                }
                Spacer(minLength: 4)
                if let journal = ref.journalOrBook {
                    Text(journal)
                        .font(.caption2)
                        .italic()
                        .foregroundStyle(.tertiary)
                        .lineLimit(1)
                }
            }
            if isExpanded, let bibtex = ref.bibtex, !bibtex.isEmpty {
                ScrollView(.horizontal, showsIndicators: false) {
                    Text(bibtex)
                        .font(.system(.caption2, design: .monospaced))
                        .foregroundStyle(.secondary)
                        .textSelection(.enabled)
                        .padding(6)
                        .background(Color(.textBackgroundColor).opacity(0.6))
                        .clipShape(RoundedRectangle(cornerRadius: 4))
                }
                .frame(maxHeight: 80)
            }
        }
        .padding(.vertical, 2)
    }

    private var refTitle: String {
        if let title = ref.title, !title.isEmpty { return title }
        if let bib = ref.bibtex, !bib.isEmpty { return String(bib.prefix(60)) + "…" }
        return "Untitled"
    }
}
