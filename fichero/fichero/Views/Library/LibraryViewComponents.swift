import SwiftUI

// MARK: - Mail-Style Row (like Apple Mail)

struct MailStyleRow: View {
    let document: Document
    let isSelected: Bool
    var onTagTap: (String) -> Void = { _ in }

    var body: some View {
        HStack(alignment: .top, spacing: 12) {
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

                // Status + Type row — tappable tags filter the list
                HStack(spacing: 8) {
                    StatusBadge(status: document.status)
                        .onTapGesture {
                            onTagTap(document.status.rawValue)
                        }

                    if document.docType == .folder {
                        Text("Folder")
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .onTapGesture { onTagTap("Folder") }
                    } else if let fileType = document.fileType {
                        Text(fileType.rawValue.capitalized)
                            .font(.caption)
                            .foregroundColor(.secondary)
                            .onTapGesture { onTagTap(fileType.rawValue.capitalized) }
                    }
                }

                // Summary/Output preview (2-3 lines)
                if let content = document.pageContent, !content.isEmpty {
                    Text(content)
                        .font(.subheadline)
                        .foregroundColor(.secondary)
                        .lineLimit(2)
                        .fixedSize(horizontal: false, vertical: true)
                }
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
}

// MARK: - Map Card (Tinderbox-style with thumbnail)

struct MapCard: View {
    let document: Document
    let isSelected: Bool
    let position: CGPoint

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
                          let pdfPath = document.metadata["pdf_path"]?.value as? String,
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
    /// current `path` resolved via `pdf_parent_id`.
    fileprivate func resolvedParentPDFPath(for doc: Document) -> String? {
        let metadataPath = doc.metadata["pdf_path"]?.value as? String
        if let metadataPath, !metadataPath.isEmpty,
           !metadataPath.contains("/fichero-drop-"),
           FileManager.default.fileExists(atPath: metadataPath) {
            return metadataPath
        }
        guard let parentId = doc.metadata["pdf_parent_id"]?.value as? String,
              let parent = documentStore.currentDocuments.first(where: { $0.id == parentId }),
              let parentPath = parent.path,
              !parentPath.isEmpty else {
            return metadataPath
        }
        return parentPath
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
