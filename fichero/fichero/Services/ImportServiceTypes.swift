import Foundation
import UniformTypeIdentifiers

// MARK: - Supporting Types

/// How sources come in (`source.sync.four-ways-in`, ruled 2026-10-03): the engine's ingest modes.
enum IngestMode: String, Codable {
    case link = "LINK"  // Create bookmark reference (zero disk usage)
    case copy = "COPY"  // Copy file into library (uses APFS cloning)
    case move = "MOVE"  // Move file into library (original deleted)
    /// The folder is worked on in place and kept in step (the adopted folder). A folder ingest
    /// only: loose files chosen this way are linked, which is what Index does to each file.
    case index = "INDEX"

    var displayName: String {
        switch self {
        case .link: return "Link Files"
        case .copy: return "Copy Files"
        case .move: return "Move Files"
        case .index: return "Index Folder"
        }
    }

    var description: String {
        switch self {
        case .link: return "Reference files in place (no disk usage)"
        case .copy: return "Duplicate files into library"
        case .move: return "Move files into library (original deleted)"
        case .index: return "Work on the folder in place and keep it up to date"
        }
    }

    var icon: String {
        switch self {
        case .link: return "link"
        case .copy: return "doc.on.doc"
        case .move: return "arrow.right.doc"
        case .index: return "arrow.triangle.2.circlepath"
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
        // Guard against total==0 (empty import) — an unguarded divide yields
        // NaN and corrupts the progress bar.
        guard total > 0 else { return 0 }
        return Double(current) / Double(total) * 100
    }

    var description: String {
        "Importing \(current)/\(total): \(currentFile)"
    }
}

/// Import error wrapper
struct ImportError: Error, LocalizedError, Identifiable {
    let id = UUID()
    let url: URL
    let error: Error

    var errorDescription: String? {
        "Failed to import \(url.lastPathComponent): \(Self.fullReason(for: error))"
    }

    /// The whole reason, not just its headline.
    ///
    /// `localizedDescription` returns ONLY `NSLocalizedDescriptionKey`. When the
    /// underlying error is the batch error from
    /// `ImportService.makeAllImportsFailedError`, that key holds the summary
    /// ("All 1 import(s) failed") while the per-file causes it carefully
    /// assembled sit in `NSLocalizedRecoverySuggestionErrorKey` — so the one
    /// part the user can act on was built, attached, and then dropped on the
    /// floor by every caller that read `localizedDescription` (2026-08-04:
    /// Daniel saw "All 1 import(s) failed" and no cause at all).
    ///
    /// Appended, not substituted: the summary says how MUCH failed and the
    /// suggestion says WHY, and neither answers the other's question.
    static func fullReason(for error: Error) -> String {
        let headline = error.localizedDescription
        let suggestion = (error as NSError).localizedRecoverySuggestion
        guard let suggestion, !suggestion.isEmpty else { return headline }
        return "\(headline)\n\(suggestion)"
    }
}

/// What an import batch actually achieved — successes AND failures together
/// (#3276).
///
/// `importFiles` used to return a bare `[Document]` and throw only when EVERY
/// file failed, so a ten-file drop that lost three returned normally and the
/// caller had no way to notice: the per-file errors went into
/// `ImportService.lastError`, which no view has ever read. "Dropped 10, got 7,
/// told nobody" is the exact shape #2384 set out to remove, surviving in the
/// partial case because only the total-failure case was wired.
///
/// Returning failures alongside documents makes the partial case impossible to
/// discard by accident: a caller that wants to ignore it has to say so.
/// Not `Sendable`: `ImportError` wraps an arbitrary `Error`, which is not.
/// Claiming the conformance would be a lie the compiler cannot check.
struct ImportOutcome {
    /// Documents the engine confirmed. A FOLDER import contributes none — the
    /// engine returns document ids asynchronously — so this is not a count of
    /// what landed, which is why `attempted` is tracked separately.
    let documents: [Document]

    /// Every per-file failure, in the order encountered. Empty on a clean run.
    let failures: [ImportError]

    /// How many URLs the batch was ASKED to import. Kept because neither
    /// `documents` nor `failures` can reconstruct it: folders succeed without
    /// producing a document here, so `documents.count + failures.count` under
    /// counts a mixed batch and would quietly under-report the denominator in
    /// any "N of M" message.
    let attempted: Int

    /// Pages that came in without their image (#5143): a TEI, PAGE or ALTO file imported on its own
    /// is a document of its pages, and the engine names each page whose scan did not come with it.
    var pagesWithoutImage: [String] = []

    var isComplete: Bool { failures.isEmpty }

    /// The engine's names for the pages without an image, read off the documents it returned.
    static func pagesWithoutImage(in documents: [Document]) -> [String] {
        documents.flatMap { document in
            (document.metadata["pages_without_image"]?.value as? [Any?] ?? []).compactMap { $0 as? String }
        }
    }

    /// The report for those pages, or nil when every page came with its image.
    var pagesWithoutImageMessage: String? {
        guard !pagesWithoutImage.isEmpty else { return nil }
        let count = pagesWithoutImage.count
        let shown = pagesWithoutImage.prefix(6).joined(separator: "\n")
        let more = count > 6 ? "\n(and \(count - 6) more)" : ""
        let pages = count == 1 ? "1 page has" : "\(count) pages have"
        return "Every page came in. \(pages) no image yet; each is named with the image the file points to:\n\(shown)\(more)"
    }

    /// A user-facing sentence for the PARTIAL case, or nil when nothing failed.
    ///
    /// Deliberately nil rather than an empty string on success: an empty
    /// message assigned into a banner reads as "there is a message and it says
    /// nothing", which is how a silent failure gets rendered as a blank alert.
    var partialFailureMessage: String? {
        guard !failures.isEmpty else { return nil }
        let succeeded = attempted - failures.count
        let firstReason = failures.first?.errorDescription ?? "Import failed"
        if succeeded <= 0 {
            return "None of the \(attempted) item(s) imported. \(firstReason)"
        }
        return "Imported \(succeeded) of \(attempted) — \(failures.count) failed. \(firstReason)"
    }

    /// One outcome for a batched import (drops split per destination folder).
    ///
    /// Exists so each call site reports the WHOLE drop rather than per batch:
    /// two banners for one gesture, or worse a clean-looking second batch
    /// overwriting the first batch's failure, is the same silence in a
    /// different shape. Documents are not carried — no caller needs them
    /// merged, and pretending otherwise would invite the folder-import
    /// undercount `attempted` exists to avoid.
    static func merged(_ outcomes: [ImportOutcome]) -> ImportOutcome {
        ImportOutcome(
            documents: [],
            failures: outcomes.flatMap(\.failures),
            attempted: outcomes.reduce(0) { $0 + $1.attempted },
            pagesWithoutImage: outcomes.flatMap(\.pagesWithoutImage)
        )
    }
}
