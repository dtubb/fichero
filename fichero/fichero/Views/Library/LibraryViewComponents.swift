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
///
/// This comment used to claim "the sidebar itself is a native
/// `.listStyle(.sidebar)` List, which already renders this treatment". That
/// assumption was wrong and is the whole of #4371: the sidebar IS fully
/// native — there is no hand-rolled fill anywhere under `Views/Sidebar` — and
/// what the native emphasized source-list selection actually renders is a
/// saturated accent bar with the label forced to white and bolded, which is
/// exactly what Daniel reported and nothing like Finder's soft grey row with
/// a green folder icon and normal black text. "Native" was already satisfied;
/// it was the premise that was stale. So the tokens below are now the app's
/// ONE selection vocabulary for every surface INCLUDING the sidebar, rather
/// than a set of catch-up tokens for the custom surfaces only.
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

    // MARK: - Sidebar rows (#4371)

    /// How a sidebar row's label renders.
    ///
    /// Two fields, both of which the native emphasized selection changes and
    /// neither of which it should: Daniel's report names bolding and
    /// colour-stripping specifically. Modelled as a value so "selection does
    /// not touch the label" is one assertable equality rather than an absence
    /// spread across a view body.
    struct SidebarRowLabel: Equatable {
        let color: Color
        let weight: Font.Weight
    }

    /// Finder/Mail: the ROW carries the selection; the item keeps its own
    /// appearance. The `isSelected` parameter is deliberately ignored — that
    /// is the rule, not an oversight, and `sidebarLabel(isSelected: true) ==
    /// sidebarLabel(isSelected: false)` is how the test states it.
    ///
    /// This is also what keeps the icon's semantic colour: nothing here
    /// re-tints it, so a green folder stays green when selected.
    static func sidebarLabel(isSelected: Bool) -> SidebarRowLabel {
        SidebarRowLabel(color: .primary, weight: .regular)
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
                        // Same fall-through as the thumbnail grid (#4416).
                        Text(DocumentTitle.displayName(for: document))
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

    private var rowThumbnail: some View {
        DocumentThumbnail(
            document: document,
            width: Self.thumbWidth,
            height: Self.thumbHeight
        )
    }
}

// MARK: - Document Thumbnail

/// What a document's thumbnail well actually renders.
///
/// Deliberately a FILE-SCOPE enum, not a static on `DocumentThumbnail`: under
/// the macOS 26 SDK any static declared on a `View` inherits the type's
/// MainActor isolation, and Swift Testing calls such a helper off-main, which
/// SIGTRAPs the whole test process. Keeping the classifier off the View makes
/// it testable with no isolation at all. This placement is load-bearing.
enum DocumentThumbnailKind: Equatable {
    case folder
    case textPreview(String)
    case storageImage

    static func forDocument(_ document: Document) -> DocumentThumbnailKind {
        if document.docType == .folder { return .folder }
        if document.fileType == .image { return .storageImage }
        // Text-preview thumbnail (#625) is only for genuinely text documents
        // (JSON/plain text) with no page image. A PDF page ALWAYS shows its
        // rendered page image via the storage endpoint — never a rendering of
        // its extracted text, even though the page also carries
        // `pageContent`. (#2052)
        if document.docType != .page,
           document.fileType != .pdf,
           let preview = document.pageContent,
           !preview.isEmpty {
            return .textPreview(preview)
        }
        return .storageImage
    }

    /// Whether rendering this well hits the storage thumbnail endpoint — the
    /// prefetch window filters on it so PDFs and pages (most of an archive)
    /// are batched too, not just `.image` documents (#4202).
    var fetchesStorageThumbnail: Bool {
        self == .storageImage
    }
}

/// Shared thumbnail well for Mail-style list rows and the table's name cell
/// (#4202). Icon tiles keep their own larger tile view.
struct DocumentThumbnail: View {
    let document: Document
    let width: CGFloat
    let height: CGFloat
    /// List rows crop-to-fill — their 28×36 well already matches page aspect.
    /// The denser table well passes `.fit` so the image letterboxes rather
    /// than cropping, consistent with #4197's scale-to-fit decision.
    var contentMode: ContentMode = .fill
    var folderSymbolSize: CGFloat = 20

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 4)
                .fill(Color(.windowBackgroundColor))

            switch DocumentThumbnailKind.forDocument(document) {
            case .folder:
                Image(systemName: "folder.fill")
                    .font(.system(size: folderSymbolSize))
                    .foregroundColor(.accentColor)
            case .textPreview(let preview):
                TextPreviewThumbnail(text: preview)
                    .frame(width: width, height: height)
                    .clipped()
            case .storageImage:
                LibraryImageView(documentId: document.id, imageType: .thumbnail)
                    .aspectRatio(contentMode: contentMode)
                    .frame(width: width, height: height)
                    .clipped()
            }
        }
        .frame(width: width, height: height)
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
