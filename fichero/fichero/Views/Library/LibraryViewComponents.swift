import SwiftUI

// MARK: - Mail-Style Row (like Apple Mail)

struct MailStyleRow: View {
    let document: Document
    let isSelected: Bool
    /// Entity types the parent wants rendered in the lozenge rows.
    /// Defaults to all six so callers that don't filter still see
    /// everything; LibraryView passes its `listVisibleEntityTypes`
    /// computed set so the top-right filter menu drives this. (#519
    /// follow-up — list view filter.)
    var visibleEntityTypes: Set<String> = ["people", "places", "organizations", "dates", "events", "keywords"]
    var onTagTap: (String) -> Void = { _ in }

    @EnvironmentObject private var documentStore: DocumentStore

    private static let thumbWidth: CGFloat = 64
    private static let thumbHeight: CGFloat = 80

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

                    Text(document.name)
                        .font(.headline)
                        .lineLimit(3)
                        .truncationMode(.middle)
                        .fixedSize(horizontal: false, vertical: true)

                    if document.isLinked {
                        Image(systemName: "arrow.up.right.square")
                            .font(.caption2)
                            .foregroundStyle(.secondary)
                    }

                    Spacer()

                    Text(document.createdAt, style: .date)
                        .font(.caption)
                        .foregroundColor(.secondary)
                }

                // Status + Type row. Display only — earlier these were
                // tappable to filter, but a single click on the badge
                // hijacked row selection and the user could end up with
                // a stuck filter ('No results for "Image"') with no
                // visible escape. ⌘F opens the filter bar for explicit
                // filtering. (#519 follow-up — Daniel: 'right now its
                // single clicking and changing'.)
                HStack(spacing: 8) {
                    StatusBadge(status: document.status)
                    if document.docType == .folder {
                        Text("Folder")
                            .font(.caption)
                            .foregroundColor(.secondary)
                    } else if let fileType = document.fileType {
                        Text(fileType.rawValue.capitalized)
                            .font(.caption)
                            .foregroundColor(.secondary)
                    }
                }

                // Summary/Output preview — bumped to 4 lines so list view
                // surfaces meaningful body, not just a glimpse.
                if let content = document.pageContent, !content.isEmpty {
                    Text(content)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(4)
                        .fixedSize(horizontal: false, vertical: true)
                }

                // Entity preview rows — surfaces the NER results from
                // extract_all (people, places, organizations, dates,
                // events, keywords) so list view shows what the workflow
                // actually found, not just count + status. Hidden when
                // no entity-typed artifacts exist for this doc. (#519)
                ArtifactEntitiesView(
                    documentId: document.id,
                    style: .multiLine,
                    visibleTypes: visibleEntityTypes
                )
            }
        }
        .padding(.vertical, 4)
        .contentShape(Rectangle())
    }

    private var statusColor: Color {
        switch document.status {
        case .pending: return .gray
        case .processing: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }

    /// Page-child docs store the parent PDF path in `metadata.pdf_path`.
    /// For dropped imports that path may be a temp dir macOS already
    /// GC'd, so fall back to the parent doc's current `path` resolved
    /// via `pdf_parent_id` — mirrors DocumentThumbnailView.resolvedParentPDFPath.
    private func resolvedParentPDFPath(for doc: Document) -> String? {
        let metadataPath = doc.metadata["pdf_path"]?.value as? String
        if let metadataPath, !metadataPath.isEmpty,
           !metadataPath.contains("/fichero-drop-"),
           FileManager.default.fileExists(atPath: metadataPath) {
            return metadataPath
        }
        // The parent PDF is the selectedCollection when we're viewing its
        // page children — currentDocuments is the *children* list, so the
        // parent isn't in it. Check selectedCollection first, then fall
        // back to currentDocuments (covers other lookup paths). (#890)
        let parentId = doc.metadata["pdf_parent_id"]?.value as? String ?? doc.parentId
        if let parentId {
            if let selected = documentStore.selectedCollection,
               selected.id == parentId,
               let selectedPath = selected.path,
               !selectedPath.isEmpty {
                return selectedPath
            }
            if let parent = documentStore.currentDocuments.first(where: { $0.id == parentId }),
               let parentPath = parent.path,
               !parentPath.isEmpty {
                return parentPath
            }
        }
        return metadataPath
    }

    @ViewBuilder
    private var rowThumbnail: some View {
        let size = CGSize(width: Self.thumbWidth, height: Self.thumbHeight)
        ZStack {
            RoundedRectangle(cornerRadius: 4)
                .fill(Color(.windowBackgroundColor))

            if document.docType == .folder {
                Image(systemName: "folder.fill")
                    .font(.system(size: 28))
                    .foregroundColor(.accentColor)
            } else if document.fileType == .pdf,
                      let path = document.path,
                      !path.isEmpty {
                PDFThumbnailView(path: path, size: size)
                    .clipped()
            } else if document.docType == .page,
                      let pdfPath = resolvedParentPDFPath(for: document),
                      !pdfPath.isEmpty {
                let pageIndex = max(0, (document.sequence ?? 1) - 1)
                PDFThumbnailView(
                    path: pdfPath, size: size, pageIndex: pageIndex
                )
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

// MARK: - Map Card (Tinderbox-style with thumbnail)

struct MapCard: View {
    let document: Document
    let isSelected: Bool
    let position: CGPoint

    @EnvironmentObject private var documentStore: DocumentStore

    /// See `MailStyleRow.resolvedParentPDFPath` — same fallback chain so
    /// page children render the correct PDF page on map cards even when
    /// the metadata path has gone stale or the parent PDF is only
    /// reachable via `selectedCollection`. (#927)
    private func resolvedParentPDFPath(for doc: Document) -> String? {
        let metadataPath = doc.metadata["pdf_path"]?.value as? String
        if let metadataPath, !metadataPath.isEmpty,
           !metadataPath.contains("/fichero-drop-"),
           FileManager.default.fileExists(atPath: metadataPath) {
            return metadataPath
        }
        let parentId = doc.metadata["pdf_parent_id"]?.value as? String ?? doc.parentId
        if let parentId {
            if let selected = documentStore.selectedCollection,
               selected.id == parentId,
               let selectedPath = selected.path,
               !selectedPath.isEmpty {
                return selectedPath
            }
            if let parent = documentStore.currentDocuments.first(where: { $0.id == parentId }),
               let parentPath = parent.path,
               !parentPath.isEmpty {
                return parentPath
            }
        }
        return metadataPath
    }

    var body: some View {
        VStack(spacing: 6) {
            // Thumbnail area
            ZStack {
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(.windowBackgroundColor))

                // PDFs + PDF page children render locally via PDFKit;
                // everything else loads thumbnail from backend API.
                if document.fileType == .pdf, let path = document.path, !path.isEmpty {
                    PDFThumbnailView(path: path, size: CGSize(width: 200, height: 280))
                        .clipped()
                } else if document.docType == .page,
                          let pdfPath = resolvedParentPDFPath(for: document),
                          !pdfPath.isEmpty {
                    let pageIndex = max(0, (document.sequence ?? 1) - 1)
                    PDFThumbnailView(
                        path: pdfPath,
                        size: CGSize(width: 200, height: 280),
                        pageIndex: pageIndex
                    )
                    .clipped()
                } else {
                    LibraryImageView(documentId: document.id, imageType: .thumbnail)
                        .aspectRatio(contentMode: .fill)
                        .clipped()
                }

                // Status indicator overlay
                VStack {
                    Spacer()
                    HStack {
                        Spacer()
                        Circle()
                            .fill(statusColor)
                            .frame(width: 12, height: 12)
                            .overlay(
                                Circle()
                                    .stroke(Color.white, lineWidth: 1.5)
                            )
                            .padding(4)
                    }
                }
            }
            .frame(width: 80, height: 80)
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? Color.accentColor : Color.gray.opacity(0.2), lineWidth: isSelected ? 2 : 1)
            )

            // Name label
            Text(document.name)
                .font(.caption)
                .lineLimit(2)
                .truncationMode(.middle)
                .multilineTextAlignment(.center)
                .frame(width: 90)
        }
        .padding(6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isSelected ? Color.accentColor.opacity(0.15) : Color.clear)
        )
        .shadow(color: .black.opacity(isSelected ? 0.15 : 0.05), radius: isSelected ? 4 : 2, x: 0, y: 1)
        .position(position)
    }

    private var statusColor: Color {
        switch document.status {
        case .pending: return .gray
        case .processing: return .blue
        case .completed: return .green
        case .failed: return .red
        }
    }
}

// MARK: - Map Grid Background

struct MapGridBackground: View {
    let gridSpacing: CGFloat = 40

    var body: some View {
        Canvas { context, size in
            // Draw grid
            let path = Path { path in
                // Vertical lines
                var xPos: CGFloat = 0
                while xPos < size.width {
                    path.move(to: CGPoint(x: xPos, y: 0))
                    path.addLine(to: CGPoint(x: xPos, y: size.height))
                    xPos += gridSpacing
                }

                // Horizontal lines
                var yPos: CGFloat = 0
                while yPos < size.height {
                    path.move(to: CGPoint(x: 0, y: yPos))
                    path.addLine(to: CGPoint(x: size.width, y: yPos))
                    yPos += gridSpacing
                }
            }

            context.stroke(path, with: .color(.gray.opacity(0.15)), lineWidth: 0.5)
        }
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

// MARK: - Document Thumbnail View

struct DocumentThumbnailView: View {
    let document: Document
    let isSelected: Bool
    var scale: CGFloat = 1.0
    @EnvironmentObject private var documentStore: DocumentStore

    /// Page-child docs store the original drop's PDF path in
    /// `metadata.pdf_path`. For dropped imports, that path is a temp dir
    /// (`/private/var/folders/.../T/fichero-drop-XXX/...`) which macOS
    /// garbage-collects, leaving a dead path. (#703 — grid filled with
    /// placeholder icons.) Try the metadata path first; if it's gone or
    /// looks like a temp drop dir, fall back to the parent PDF doc's
    /// current `path` resolved via `pdf_parent_id` — checking
    /// `selectedCollection` first because that's where the parent PDF
    /// lives when we're viewing its children (currentDocuments is the
    /// children list, not a peer of the parent). (#927 mirrors the
    /// MailStyleRow fix from #890.)
    fileprivate func resolvedParentPDFPath(for doc: Document) -> String? {
        let metadataPath = doc.metadata["pdf_path"]?.value as? String
        if let metadataPath, !metadataPath.isEmpty,
           !metadataPath.contains("/fichero-drop-"),
           FileManager.default.fileExists(atPath: metadataPath) {
            return metadataPath
        }
        let parentId = doc.metadata["pdf_parent_id"]?.value as? String ?? doc.parentId
        if let parentId {
            if let selected = documentStore.selectedCollection,
               selected.id == parentId,
               let selectedPath = selected.path,
               !selectedPath.isEmpty {
                return selectedPath
            }
            if let parent = documentStore.currentDocuments.first(where: { $0.id == parentId }),
               let parentPath = parent.path,
               !parentPath.isEmpty {
                return parentPath
            }
        }
        return metadataPath
    }

    var body: some View {
        VStack(spacing: 6) {
            ZStack {
                // Use a portrait aspect (3:4) so document/photo thumbnails
                // get a rectangle that matches typical page proportions —
                // not a square. Square forced one-row icon list to crop
                // photos awkwardly. (#718)
                RoundedRectangle(cornerRadius: 6)
                    .fill(Color(.windowBackgroundColor))
                    .aspectRatio(3.0 / 4.0, contentMode: .fit)

                // Show folder icon for folders, thumbnail for files.
                // For PDFs + PDF page children, render locally via PDFKit.
                if document.docType == .folder {
                    Image(systemName: "folder.fill")
                        .font(.system(size: 48 * scale))
                        .foregroundColor(.accentColor)
                } else if document.fileType == .pdf, let path = document.path, !path.isEmpty {
                    PDFThumbnailView(path: path, size: CGSize(width: 240, height: 320))
                        .clipped()
                } else if document.docType == .page,
                          let pdfPath = resolvedParentPDFPath(for: document),
                          !pdfPath.isEmpty {
                    let pageIndex = max(0, (document.sequence ?? 1) - 1)
                    PDFThumbnailView(
                        path: pdfPath,
                        size: CGSize(width: 240, height: 320),
                        pageIndex: pageIndex
                    )
                    .clipped()
                } else {
                    // Load thumbnail from backend API with library path header.
                    // Pin to the cell's 3:4 aspect via the inner GeometryReader-
                    // style frame so wide-aspect images (panoramas, landscape
                    // photos) don't blow past the cell width and overlap the
                    // neighbour to the right (#789). `.fill` + `.clipped()`
                    // alone wasn't enough — without an explicit frame, the
                    // intrinsic image size won the layout pass.
                    LibraryImageView(documentId: document.id, imageType: .thumbnail)
                        .aspectRatio(contentMode: .fill)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .clipped()
                }

                VStack {
                    Spacer()
                    HStack {
                        if document.isLinked {
                            Image(systemName: "arrow.up.right.square")
                                .font(.system(size: 9, weight: .semibold))
                                .foregroundStyle(.secondary)
                                .shadow(color: Color(.windowBackgroundColor), radius: 1)
                                .padding(5)
                        }
                        Spacer()
                        statusIndicator
                            .padding(4)
                    }
                }
            }
            .clipShape(RoundedRectangle(cornerRadius: 6))
            .overlay(
                RoundedRectangle(cornerRadius: 6)
                    .stroke(isSelected ? Color.accentColor : Color.clear, lineWidth: 2)
            )

            Text(document.name)
                .font(.caption)
                .lineLimit(2)
                .truncationMode(.middle)
                .multilineTextAlignment(.center)
                .foregroundColor(isSelected ? .accentColor : .primary)
        }
        .frame(width: 100 * scale)
        .padding(6)
        .background(
            RoundedRectangle(cornerRadius: 8)
                .fill(isSelected ? Color.accentColor.opacity(0.1) : Color.clear)
        )
    }

    @ViewBuilder
    private var statusIndicator: some View {
        switch document.status {
        case .processing:
            ProgressView()
                .scaleEffect(0.5)
                .background(.ultraThinMaterial)
                .cornerRadius(4)
        case .completed:
            Image(systemName: "checkmark.circle.fill")
                .foregroundColor(.green)
                .font(.caption)
        case .failed:
            Image(systemName: "xmark.circle.fill")
                .foregroundColor(.red)
                .font(.caption)
        case .pending:
            EmptyView()
        }
    }
}
