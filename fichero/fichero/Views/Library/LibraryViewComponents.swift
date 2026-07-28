import FicheroAPIClient
import SwiftUI

// MARK: - Mail-style selection (#4191)

/// The ONE selection treatment for library list rows, icon tiles, and table
/// rows, matching Apple Mail's sidebar: the selected item carries a SUBTLE
/// grey rounded-rect fill in every pane state, and the focused/unfocused
/// distinction lives in the LABEL — accent-tinted when the pane is focused
/// (HIG: only key-window controls carry color), secondary otherwise. This
/// replaces the #3875 solid-accent fill and the #4160 white-on-accent text
/// inversion that only existed because black-on-accent was illegible.
/// The sidebar itself is a native `.listStyle(.sidebar)` List, which already
/// renders this treatment — these tokens bring the custom surfaces in line.
enum LibrarySelectionStyle {
    /// AppKit's own unemphasized-selection color, so light/dark mode and
    /// increased-contrast track the system for free.
    static var fill: Color {
        #if os(macOS)
        Color(nsColor: .unemphasizedSelectedContentBackgroundColor)
        #else
        Color(.secondarySystemFill)
        #endif
    }

    static let cornerRadius: CGFloat = 6

    static func labelTint(focused: Bool) -> Color {
        focused ? .accentColor : .secondary
    }
}

// MARK: - Mail-Style Row (like Apple Mail)

struct MailStyleRow: View {
    let document: Document
    let isSelected: Bool
    /// Mail-style selection (#4191): the focused selection tints the TITLE
    /// accent over the subtle grey fill — never a white-on-accent inversion.
    /// Safe with the row's `.equatable()` diffing: focus changes also change
    /// the `tint` LibrarySelectableRow already compares.
    var isPaneFocused: Bool = false
    /// Inline rename (#4160): the context menu's Rename set state only the
    /// TABLE mode consumed — in list mode it silently did nothing (while
    /// still blocking type-select). Threaded from LibraryView's existing
    /// renamingDocumentId/editingName wiring, same as the table column.
    var isRenaming: Bool = false
    var editingName: Binding<String> = .constant("")
    var onCommitRename: () -> Void = {}
    var onCancelRename: () -> Void = {}
    /// Entity types the parent wants rendered in the lozenge rows.
    /// Defaults to all six so callers that don't filter still see
    /// everything; LibraryView passes its `listVisibleEntityTypes`
    /// computed set so the top-right filter menu drives this. (#519
    /// follow-up — list view filter.)
    var visibleEntityTypes: Set<String> = ["people", "places", "organizations", "dates", "events", "keywords"]
    var onTagTap: (String) -> Void = { _ in }

    // Compact leading thumbnail so the title/text gets the row's width
    // (Mail-style — the icon was previously 40×50 and crowded the title). (#1459)
    private static let thumbWidth: CGFloat = 28
    private static let thumbHeight: CGFloat = 36

    /// Fixed window for the entity-lozenge block (#4191 density cap) — the
    /// same ~two-row estimate ArtifactEntitiesView reserves while loading,
    /// so the row's height is identical before and after artifacts land.
    static let entityBlockHeight: CGFloat = 40

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
            // Thumbnail to the left — same source as the icon view's
            // DocumentThumbnailView, sized down to fit a list row.
            // Apple Mail / Photos / NetNewsWire convention. (#519 follow-up)
            rowThumbnail
                .padding(.top, 2)

            // Status indicator: spinner while processing, dot otherwise (#518).
            // Live indicator pairs with LibraryView's processing-poll timer so
            // the user sees motion + status flips without manual refresh.
            Group {
                if document.status == .processing {
                    ProgressView()
                        .scaleEffect(0.55)
                        .frame(width: 10, height: 10)
                } else {
                    Circle()
                        .fill(statusColor)
                        .frame(width: 10, height: 10)
                }
            }
            .padding(.top, 5)

            // Content
            VStack(alignment: .leading, spacing: 4) {
                // Title row
                HStack {
                    // Folder icon for folders
                    if document.docType == .folder {
                        Image(systemName: "folder.fill")
                            .foregroundColor(.accentColor)
                    }

                    // PDF page rows show their page number (prefer an
                    // extracted page_label once #2080 lands), not the
                    // internal id/filename. Non-page docs keep their name. (#2053)
                    if isRenaming {
                        EditableDocumentName(
                            document: document,
                            isRenaming: true,
                            editingName: editingName,
                            font: .headline,
                            onCommit: onCommitRename,
                            onCancel: onCancelRename
                        )
                    } else {
                        Text(document.pageThumbnailLabel ?? document.name)
                            .font(.headline)
                            .foregroundStyle(titleColor)
                            // Uniform rows (#4191 density cap): the title
                            // always occupies exactly two lines so every row
                            // is the same height — scroll position is stable
                            // and PageUp/Down's row step stays honest.
                            .lineLimit(2, reservesSpace: true)
                            .truncationMode(.middle)
                            // Middle-truncated titles reveal in full on hover.
                            .help(document.pageThumbnailLabel ?? document.name)
                    }

                    if document.isLinked {
                        Image(systemName: "arrow.up.right.square")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    Text(document.createdAt, style: .date)
                        .font(.caption)
                        .foregroundStyle(.secondary)
                }

                // Status + Type row. Display only — earlier these were
                // tappable to filter, but a single click on the badge
                // hijacked row selection and the user could end up with
                // a stuck filter ('No results for "Image"') with no
                // visible escape. ⌘F opens the filter bar for explicit
                // filtering. (#519 follow-up — the maintainer: 'right now its
                // single clicking and changing'.)
                HStack(spacing: 8) {
                    StatusBadge(status: document.status)
                    if document.docType == .folder {
                        Text("Folder")
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    } else if let fileType = document.fileType {
                        Text(fileType.rawValue.capitalized)
                            .font(.caption)
                            .foregroundStyle(.secondary)
                    }
                }

                // Summary/Output preview — ALWAYS two reserved lines
                // (#4191 density cap): docs without body text keep the same
                // row height as docs with it, so nothing re-pitches as
                // content loads and the scroll position never jumps.
                Text(document.pageContent ?? "")
                    .font(.subheadline)
                    .foregroundStyle(.secondary)
                    .lineLimit(2, reservesSpace: true)

                // Entity preview rows — surfaces the NER results from
                // extract_all (people, places, organizations, dates,
                // events, keywords) so list view shows what the workflow
                // actually found, not just count + status. (#519)
                // The block is a FIXED-height window (#4191 density cap),
                // matching the ~two-lozenge-row reservation the loading
                // state already uses — rows stay one height whether the
                // doc has zero or twenty entities, before AND after the
                // async fetch lands. ponytail: rows past the window are
                // clipped; the Inspector shows the full set.
                ArtifactEntitiesView(
                    documentId: document.id,
                    style: .multiLine,
                    visibleTypes: visibleEntityTypes
                )
                .frame(height: Self.entityBlockHeight, alignment: .topLeading)
                .clipped()
            }
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
        // VoiceOver reads one coherent row (#4160), matching the sidebar's
        // terse label+hint convention — not loose text fragments.
        .accessibilityElement(children: .combine)
        .accessibilityLabel(rowAccessibilityLabel)
        .accessibilityValue(document.status.rawValue.capitalized)
        .accessibilityHint(rowAccessibilityHint)
        .accessibilityAddTraits(isSelected ? .isSelected : [])
        .accessibilityIdentifier("libraryRow.\(document.id)")
    }

    private var rowAccessibilityLabel: String {
        let name = document.pageThumbnailLabel ?? document.name
        if document.docType == .folder { return "\(name), folder" }
        if let fileType = document.fileType { return "\(name), \(fileType.rawValue)" }
        return name
    }

    private var rowAccessibilityHint: String {
        #if os(macOS)
        "Press Return to open, Space to preview. Right-click for actions."
        #else
        "Double tap and hold for actions."
        #endif
    }

    /// Mail-style (#4191): a selected row keeps normal text over the grey
    /// fill and signals focus through the title's tint — accent when the
    /// pane is focused, secondary when it isn't. Secondary text stays
    /// `.secondary` in every state.
    private var titleColor: Color {
        isSelected ? LibrarySelectionStyle.labelTint(focused: isPaneFocused) : .primary
    }

    private var statusColor: Color {
        switch document.status {
        case .pending: return .gray
        case .processing: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }

    @ViewBuilder
    private var rowThumbnail: some View {
        let size = CGSize(width: Self.thumbWidth, height: Self.thumbHeight)
        ZStack {
            RoundedRectangle(cornerRadius: 4)
                .fill(Color(.windowBackgroundColor))

            if document.docType == .folder {
                Image(systemName: "folder.fill")
                    .font(.system(size: 20))
                    .foregroundColor(.accentColor)
            } else if document.fileType == .image {
                LibraryImageView(documentId: document.id, imageType: .thumbnail)
                    .aspectRatio(contentMode: .fill)
                    .frame(width: size.width, height: size.height)
                    .clipped()
            } else if document.docType != .page, document.fileType != .pdf, let preview = document.pageContent, !preview.isEmpty {
                // Text-preview thumbnail (#625) is only for genuinely text
                // documents (JSON/plain text) with no page image. A PDF page
                // ALWAYS shows its rendered page image via the storage
                // endpoint below — never a rendering of its extracted text,
                // even though the page also carries `pageContent`. (#2052)
                TextPreviewThumbnail(text: preview)
                    .frame(width: size.width, height: size.height)
                    .clipped()
            } else {
                LibraryImageView(documentId: document.id, imageType: .thumbnail)
                    .aspectRatio(contentMode: .fill)
                    .frame(width: size.width, height: size.height)
                    .clipped()
            }
        }
        .frame(width: Self.thumbWidth, height: Self.thumbHeight)
        .clipShape(RoundedRectangle(cornerRadius: 4))
    }
}

// MARK: - Progress Cell

struct ProgressCell: View {
    let document: Document

    var body: some View {
        switch document.status {
        case .processing:
            HStack(spacing: 6) {
                ProgressView()
                    .scaleEffect(0.6)
                Text("...")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        case .completed:
            HStack(spacing: 4) {
                Image(systemName: "checkmark.circle.fill")
                    .foregroundColor(.green)
                    .font(.caption)
                Text("100%")
                    .font(.caption)
                    .foregroundColor(.secondary)
            }
        case .failed:
            HStack(spacing: 4) {
                Image(systemName: "xmark.circle.fill")
                    .foregroundColor(.red)
                    .font(.caption)
                Text("Failed")
                    .font(.caption)
                    .foregroundColor(.red)
            }
        case .pending:
            Text("Pending")
                .font(.caption)
                .foregroundColor(.secondary)
        }
    }
}
