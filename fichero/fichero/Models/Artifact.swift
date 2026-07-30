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
    /// Typed OCR/transcription geometry (#4309). Populated only on the
    /// single-artifact fetch — list endpoints omit it to stay lean.
    var ocrGeometry: OCRGeometry?

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
        case ocrGeometry = "ocr_geometry"
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
        ocrGeometry: OCRGeometry? = nil,
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
        self.ocrGeometry = ocrGeometry
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

// MARK: - Inspector provenance

enum ArtifactProvenanceRelation: Equatable {
    case currentDocument
    case currentPage
    case descendantPage
    case linkedDocument
}

struct ArtifactProvenanceDisplay: Equatable {
    let sourceDocumentId: String
    let sourceLabel: String
    let pageLabel: String?
    let relation: ArtifactProvenanceRelation
    let workflowLabel: String?
    let providerLabel: String?

    var rowSubtitle: String? {
        let parts = [sourceLabel, workflowLabel, providerLabel]
            .compactMap { value in
                let trimmed = value?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
                return trimmed.isEmpty ? nil : trimmed
            }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

enum ArtifactProvenance {
    static func display(
        for artifact: Artifact,
        inspectedDocument: Document,
        documentsById: [String: Document]
    ) -> ArtifactProvenanceDisplay {
        let sourceDocument = documentsById[artifact.documentId]
        let pageLabel = sourceDocument?.pageThumbnailLabel

        let relation: ArtifactProvenanceRelation
        let sourceLabel: String
        if artifact.documentId == inspectedDocument.id {
            if inspectedDocument.docType == .page {
                relation = .currentPage
                sourceLabel = "This page"
            } else {
                relation = .currentDocument
                sourceLabel = "This document"
            }
        } else if sourceDocument?.docType == .page {
            relation = .descendantPage
            sourceLabel = pageLabel.map { "Page \($0)" } ?? "Child page"
        } else if let sourceDocument,
                  !sourceDocument.name.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty {
            relation = .linkedDocument
            sourceLabel = sourceDocument.name
        } else {
            relation = .linkedDocument
            sourceLabel = "Linked document"
        }

        let workflowLabel = normalized(artifact.stepName)
        let providerLabel = [normalized(artifact.provider), normalized(artifact.model)]
            .compactMap { $0 }
            .joined(separator: " · ")

        return ArtifactProvenanceDisplay(
            sourceDocumentId: artifact.documentId,
            sourceLabel: sourceLabel,
            pageLabel: pageLabel,
            relation: relation,
            workflowLabel: workflowLabel,
            providerLabel: providerLabel.isEmpty ? nil : providerLabel
        )
    }

    private static func normalized(_ value: String?) -> String? {
        guard let value else { return nil }
        let trimmed = value.trimmingCharacters(in: .whitespacesAndNewlines)
        return trimmed.isEmpty ? nil : trimmed
    }
}
