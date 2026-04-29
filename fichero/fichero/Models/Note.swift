import Foundation

// MARK: - Note Model

/// User annotation on any object.
/// Matches Python Note model in fichero/models.py
///
/// Can be attached to Documents or Artifacts.
/// Can have a position (bbox) for image annotations.
struct Note: Identifiable, Codable, Hashable {
    let id: String

    // Target
    var targetType: String
    var targetId: String

    // Content
    var content: String
    var noteType: String

    // Position (for image annotations)
    var bbox: [Int]?

    // Timestamps
    var createdAt: Date
    var updatedAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case targetType = "target_type"
        case targetId = "target_id"
        case content
        case noteType = "note_type"
        case bbox
        case createdAt = "created_at"
        case updatedAt = "updated_at"
    }

    init(
        id: String = UUID().uuidString,
        targetType: String,
        targetId: String,
        content: String,
        noteType: String = "comment",
        bbox: [Int]? = nil,
        createdAt: Date = Date(),
        updatedAt: Date = Date()
    ) {
        self.id = id
        self.targetType = targetType
        self.targetId = targetId
        self.content = content
        self.noteType = noteType
        self.bbox = bbox
        self.createdAt = createdAt
        self.updatedAt = updatedAt
    }
}

// MARK: - Note Type Helpers

extension Note {
    /// Common note types
    enum NoteType: String, CaseIterable {
        case comment
        case question
        case flag
        case correction

        var displayName: String {
            switch self {
            case .comment: return "Comment"
            case .question: return "Question"
            case .flag: return "Flag"
            case .correction: return "Correction"
            }
        }

        var icon: String {
            switch self {
            case .comment: return "text.bubble"
            case .question: return "questionmark.circle"
            case .flag: return "flag"
            case .correction: return "pencil.circle"
            }
        }

        var color: String {
            switch self {
            case .comment: return "blue"
            case .question: return "orange"
            case .flag: return "red"
            case .correction: return "green"
            }
        }
    }

    /// Target type as enum
    enum TargetType: String {
        case document = "Document"
        case artifact = "Artifact"
    }

    /// Display name for the note type
    var noteTypeDisplayName: String {
        NoteType(rawValue: noteType)?.displayName ?? noteType.capitalized
    }

    /// Icon for the note type
    var noteTypeIcon: String {
        NoteType(rawValue: noteType)?.icon ?? "note.text"
    }

    /// Color for the note type
    var noteTypeColor: String {
        NoteType(rawValue: noteType)?.color ?? "gray"
    }

    /// Whether this note has a position
    var hasPosition: Bool {
        bbox != nil
    }

    /// Check if this note is attached to a document
    var isDocumentNote: Bool {
        targetType == TargetType.document.rawValue
    }

    /// Check if this note is attached to an artifact
    var isArtifactNote: Bool {
        targetType == TargetType.artifact.rawValue
    }
}
