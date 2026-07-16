import Foundation

// MARK: - Helper Types

/// Represents a document with its context in the hierarchy.
struct DocumentHierarchy {
    let ancestors: [Document]  // Sorted from root to immediate parent
    let document: Document
    let children: [Document]

    /// The immediate parent, if any.
    var parent: Document? {
        ancestors.last
    }

    /// Breadcrumb path from root to this document.
    var breadcrumb: [Document] {
        ancestors + [document]
    }
}

// `DocumentStoreError` lived here until #3919. Every one of its cases was thrown
// from exactly one place — `DocumentStore.importFile(at:)`, a hand-rolled
// multipart importer superseded by `ImportServiceGenerated` and left with no
// callers — so the whole enum went unthrowable when that function was deleted.
