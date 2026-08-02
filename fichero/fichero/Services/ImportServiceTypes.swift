import Foundation
import UniformTypeIdentifiers

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
        "Failed to import \(url.lastPathComponent): \(error.localizedDescription)"
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

    var isComplete: Bool { failures.isEmpty }

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
            attempted: outcomes.reduce(0) { $0 + $1.attempted }
        )
    }
}
