import Foundation
import UniformTypeIdentifiers
import OSLog

/// Service for file and folder import
/// Wraps the Python backend ingest API
@MainActor
class ImportService: ObservableObject {
    // MARK: - Published State

    @Published var isImporting: Bool = false
    @Published var importProgress: ImportProgress?
    @Published var lastError: ImportError?

    private let api: APIClient
    private let logger = Logger(subsystem: "ca.tubb.Fichero", category: "ImportService")

    init(apiClient: APIClient) {
        self.api = apiClient
    }

    // MARK: - Import Files

    /// Import multiple files from URLs
    /// - Parameters:
    ///   - urls: File URLs to import
    ///   - mode: LINK or COPY mode
    ///   - parentId: Optional parent collection ID
    ///   - extractText: Extract searchable text
    ///   - autoEmbed: Create vector embeddings
    ///   - onProgress: Progress callback (current, total)
    /// - Returns: Array of imported documents
    func importFiles(
        _ urls: [URL],
        mode: IngestMode = .link,
        parentId: String? = nil,
        extractText: Bool = false,
        autoEmbed: Bool = false,
        onProgress: ((Int, Int) -> Void)? = nil
    ) async throws -> [Document] {
        isImporting = true
        defer { isImporting = false }

        var imported: [Document] = []
        var errors: [ImportError] = []

        logger.info("Starting import of \(urls.count) files")

        for (index, url) in urls.enumerated() {
            do {
                // Update progress
                onProgress?(index + 1, urls.count)
                importProgress = ImportProgress(
                    current: index + 1,
                    total: urls.count,
                    currentFile: url.lastPathComponent
                )

                // Check if URL is a directory
                var isDirectory: ObjCBool = false
                let exists = FileManager.default.fileExists(atPath: url.path, isDirectory: &isDirectory)

                if exists && isDirectory.boolValue {
                    // Import folder using dedicated folder endpoint
                    logger.info("Detected folder: \(url.lastPathComponent), using folder import")
                    let folderDocs = try await importFolderCore(
                        url,
                        mode: mode,
                        parentId: parentId,
                        recursive: true,
                        extractText: extractText,
                        autoEmbed: autoEmbed
                    )
                    imported.append(contentsOf: folderDocs)
                    logger.info(
                        "Successfully imported folder with \(folderDocs.count) documents: \(url.lastPathComponent)"
                    )
                } else {
                    // Call Python backend: POST /api/ingest/file
                    let doc = try await importFile(
                        url,
                        mode: mode,
                        parentId: parentId,
                        extractText: extractText,
                        autoEmbed: autoEmbed
                    )
                    imported.append(doc)
                    logger.info("Successfully imported: \(url.lastPathComponent)")
                }

            } catch {
                logger.error("Failed to import \(url.lastPathComponent): \(error.localizedDescription)")
                errors.append(ImportError(url: url, error: error))
            }
        }

        importProgress = nil

        if !errors.isEmpty {
            lastError = errors.first
            logger.warning("Import completed with \(errors.count) errors")
            // Throw aggregate error if ALL files failed
            if imported.isEmpty {
                throw ImportError(
                    url: urls.first ?? URL(fileURLWithPath: ""),
                    error: NSError(
                        domain: "ImportService",
                        code: -1,
                        userInfo: [NSLocalizedDescriptionKey: "All imports failed"]
                    )
                )
            }
        }

        logger.info("Import completed: \(imported.count) successful, \(errors.count) failed")
        return imported
    }

    /// Import a single file
    private func importFile(
        _ url: URL,
        mode: IngestMode,
        parentId: String?,
        extractText: Bool,
        autoEmbed: Bool
    ) async throws -> Document {
        // Ensure file is accessible
        guard url.startAccessingSecurityScopedResource() else {
            throw ImportError(
                url: url,
                error: NSError(
                    domain: "ImportService",
                    code: -1,
                    userInfo: [NSLocalizedDescriptionKey: "Cannot access file"]
                )
            )
        }
        defer { url.stopAccessingSecurityScopedResource() }

        // Call Python backend: POST /api/ingest/file
        let request = IngestFileRequest(
            path: url.path,
            mode: mode.rawValue,
            parentId: parentId,
            extractText: extractText,
            autoEmbed: autoEmbed,
            save: true
        )

        return try await api.post("/ingest/file", body: request)
    }

    // MARK: - Import Folder

    /// Import an entire folder
    /// - Parameters:
    ///   - url: Folder URL to import
    ///   - mode: LINK or COPY mode
    ///   - parentId: Optional parent collection ID
    ///   - recursive: Process subdirectories
    ///   - extractText: Extract searchable text
    ///   - autoEmbed: Create vector embeddings
    ///   - onProgress: Progress callback (current, total)
    /// - Returns: Array of imported documents
    func importFolder(
        _ url: URL,
        mode: IngestMode = .link,
        parentId: String? = nil,
        recursive: Bool = true,
        extractText: Bool = false,
        autoEmbed: Bool = false,
        onProgress: ((Int, Int) -> Void)? = nil
    ) async throws -> [Document] {
        isImporting = true
        defer { isImporting = false }

        return try await importFolderCore(
            url,
            mode: mode,
            parentId: parentId,
            recursive: recursive,
            extractText: extractText,
            autoEmbed: autoEmbed
        )
    }

    /// Core folder import logic - doesn't manage isImporting flag
    /// Used internally when called from importFiles which already manages the flag
    // swiftlint:disable:next function_parameter_count
    private func importFolderCore(
        _ url: URL,
        mode: IngestMode,
        parentId: String?,
        recursive: Bool,
        extractText: Bool,
        autoEmbed: Bool
    ) async throws -> [Document] {
        logger.info("Starting folder import: \(url.lastPathComponent)")

        // Ensure folder is accessible
        guard url.startAccessingSecurityScopedResource() else {
            throw ImportError(
                url: url,
                error: NSError(
                    domain: "ImportService",
                    code: -1,
                    userInfo: [NSLocalizedDescriptionKey: "Cannot access folder"]
                )
            )
        }
        defer { url.stopAccessingSecurityScopedResource() }

        // Call Python backend: POST /api/ingest/folder
        let request = IngestFolderRequest(
            path: url.path,
            copyMode: mode == .copy,
            parentId: parentId,
            recursive: recursive,
            extractText: extractText,
            autoEmbed: autoEmbed
        )

        let documents: [Document] = try await api.post("/ingest/folder", body: request)
        logger.info("Folder import completed: \(documents.count) documents")
        return documents
    }

    // MARK: - Progress Tracking

    /// Clear import progress and errors
    func clearProgress() {
        importProgress = nil
        lastError = nil
    }
}

// MARK: - Supporting Types

/// Ingest mode - LINK creates bookmark reference, COPY imports file into library
enum IngestMode: String, Codable {
    case link = "LINK"  // Create bookmark reference (zero disk usage)
    case copy = "COPY"  // Copy file into library (uses APFS cloning)
    case move = "MOVE"  // Move file into library (original deleted)

    var displayName: String {
        switch self {
        case .link: return "Link Files"
        case .copy: return "Copy Files"
        case .move: return "Move Files"
        }
    }

    var description: String {
        switch self {
        case .link: return "Reference files in place (no disk usage)"
        case .copy: return "Duplicate files into library"
        case .move: return "Move files into library (original deleted)"
        }
    }

    var icon: String {
        switch self {
        case .link: return "link"
        case .copy: return "doc.on.doc"
        case .move: return "arrow.right.doc"
        }
    }
}

/// Request body for file import
struct IngestFileRequest: Codable {
    let path: String
    let mode: String
    let parentId: String?
    let extractText: Bool
    let autoEmbed: Bool
    let save: Bool

    enum CodingKeys: String, CodingKey {
        case path
        case mode
        case parentId = "parent_id"
        case extractText = "extract_text"
        case autoEmbed = "auto_embed"
        case save
    }
}

/// Request body for folder import
struct IngestFolderRequest: Codable {
    let path: String
    let copyMode: Bool
    let parentId: String?
    let recursive: Bool
    let extractText: Bool
    let autoEmbed: Bool

    enum CodingKeys: String, CodingKey {
        case path
        case copyMode = "copy_mode"
        case parentId = "parent_id"
        case recursive
        case extractText = "extract_text"
        case autoEmbed = "auto_embed"
    }
}

/// Import progress information
struct ImportProgress {
    let current: Int
    let total: Int
    let currentFile: String

    var percentage: Double {
        Double(current) / Double(total) * 100
    }

    var description: String {
        "Importing \(current)/\(total): \(currentFile)"
    }
}

/// Import error wrapper
struct ImportError: Error, Identifiable {
    let id = UUID()
    let url: URL
    let error: Error

    var localizedDescription: String {
        "Failed to import \(url.lastPathComponent): \(error.localizedDescription)"
    }
}
