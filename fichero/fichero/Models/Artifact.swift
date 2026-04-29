import Foundation

// MARK: - Artifact Model

/// Output from any processing step - versioned and chainable.
/// Matches Python Artifact model in fichero/models.py
///
/// Artifacts are results from AI/ML processing:
/// - Transcription (OCR text)
/// - Entities (people, places, dates)
/// - Summary
/// - Translation
/// - Grouping suggestions
/// - Segmentation suggestions
struct Artifact: Identifiable, Codable, Hashable {
    let id: String
    var documentId: String

    // Versioning/chaining
    var sourceArtifactId: String?
    var version: Int

    // Type
    var artifactType: String

    // Content
    var content: String?
    var data: [String: AnyCodable]?

    // Provenance
    var runId: String?
    var provider: String?
    var model: String?
    var stepName: String?

    // Quality
    var confidence: Double?
    var reviewed: Bool

    // Timestamps
    var createdAt: Date

    enum CodingKeys: String, CodingKey {
        case id
        case documentId = "document_id"
        case sourceArtifactId = "source_artifact_id"
        case version
        case artifactType = "artifact_type"
        case content
        case data
        case runId = "run_id"
        case provider
        case model
        case stepName = "step_name"
        case confidence
        case reviewed
        case createdAt = "created_at"
    }

    init(
        id: String = UUID().uuidString,
        documentId: String,
        sourceArtifactId: String? = nil,
        version: Int = 1,
        artifactType: String,
        content: String? = nil,
        data: [String: AnyCodable]? = nil,
        runId: String? = nil,
        provider: String? = nil,
        model: String? = nil,
        stepName: String? = nil,
        confidence: Double? = nil,
        reviewed: Bool = false,
        createdAt: Date = Date()
    ) {
        self.id = id
        self.documentId = documentId
        self.sourceArtifactId = sourceArtifactId
        self.version = version
        self.artifactType = artifactType
        self.content = content
        self.data = data
        self.runId = runId
        self.provider = provider
        self.model = model
        self.stepName = stepName
        self.confidence = confidence
        self.reviewed = reviewed
        self.createdAt = createdAt
    }
}

// MARK: - Artifact Type Helpers

extension Artifact {
    /// Common artifact types
    enum ArtifactType: String {
        case transcription
        case entities
        case summary
        case translation
        case grouping
        case segmentation
        case classification
        case embedding
    }

    /// Check if this is a transcription artifact
    var isTranscription: Bool {
        artifactType == ArtifactType.transcription.rawValue
    }

    /// Check if this is an entities artifact
    var isEntities: Bool {
        artifactType == ArtifactType.entities.rawValue
    }

    /// Display name for the artifact type
    var artifactTypeDisplayName: String {
        switch artifactType {
        case "transcription": return "Transcription"
        case "entities": return "Entities"
        case "summary": return "Summary"
        case "translation": return "Translation"
        case "grouping": return "Grouping"
        case "segmentation": return "Segmentation"
        case "classification": return "Classification"
        case "embedding": return "Embedding"
        default: return artifactType.capitalized
        }
    }

    /// Icon for the artifact type
    var artifactTypeIcon: String {
        switch artifactType {
        case "transcription": return "text.quote"
        case "entities": return "person.3"
        case "summary": return "doc.text"
        case "translation": return "globe"
        case "grouping": return "rectangle.stack"
        case "segmentation": return "rectangle.split.3x3"
        case "classification": return "tag"
        case "embedding": return "arrow.triangle.branch"
        default: return "doc"
        }
    }
}
