import Foundation

//  Extracted from Document.swift for file_length (#5113). Behaviour unchanged:
//  the declarations below are byte-for-byte what they were, moved so the file
//  that carries the Document model itself stays readable.

// MARK: - Document Types

/// Document type enum matching Python DocType
enum DocType: String, Codable, CaseIterable {
    case folder
    case group
    case file
    case page
    case chunk

    var icon: String {
        switch self {
        case .folder: return "folder"
        case .group: return "rectangle.stack"
        case .file: return "doc"
        case .page: return "doc.text"
        case .chunk: return "text.quote"
        }
    }
}

/// File type enum matching Python FileType
enum FileType: String, Codable, CaseIterable {
    case image
    case pdf
    case text
    case json
    case word
    case audio
    case video
    case epub
    case spreadsheet
    case presentation
    case csv
    case rtf
    case mobi
    case other

    var icon: String {
        switch self {
        case .image: return "photo"
        case .pdf: return "doc.richtext"
        case .text: return "doc.plaintext"
        case .json: return "curlybraces"
        case .word: return "doc.text.fill"
        case .audio: return "waveform"
        case .video: return "film"
        case .epub: return "book"
        case .spreadsheet: return "tablecells"
        case .presentation: return "rectangle.on.rectangle"
        case .csv: return "tablecells"
        case .rtf: return "doc.text"
        case .mobi: return "books.vertical"
        case .other: return "doc"
        }
    }
}

/// Programmatic chapter/section/subsection tree persisted on a PDF document.
struct DocumentStructureNode: Identifiable, Codable, Hashable {
    let id: String
    let title: String
    let kind: String
    let level: Int
    let pageRange: PageRange
    let basis: String?
    let confidence: Double?
    let sourcePageLabel: String?
    let children: [DocumentStructureNode]

    struct PageRange: Codable, Hashable {
        let start: Int
        let end: Int
    }

    enum CodingKeys: String, CodingKey {
        case id
        case title
        case kind
        case level
        case pageRange = "page_range"
        case basis
        case confidence
        case sourcePageLabel = "source_page_label"
        case children
    }
}

/// Processing status enum matching Python Status
enum Status: String, Codable, CaseIterable {
    case pending
    case processing
    case completed
    case failed

    var color: String {
        switch self {
        case .pending: return "gray"
        case .processing: return "blue"
        case .completed: return "green"
        case .failed: return "red"
        }
    }
}
