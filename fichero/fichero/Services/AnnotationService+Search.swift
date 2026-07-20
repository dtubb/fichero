import Foundation

extension AnnotationService {
    static func matchesSearch(_ annotation: DocumentAnnotation, query: String) -> Bool {
        let trimmed = query.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmed.isEmpty else { return true }
        let needle = trimmed.lowercased()

        if annotation.text?.lowercased().contains(needle) == true { return true }
        if annotation.pageLabel?.lowercased().contains(needle) == true { return true }
        if annotation.kind.label.lowercased().contains(needle) { return true }
        if annotation.tags.contains(where: { $0.lowercased().contains(needle) }) { return true }
        if annotation.linkedClaimIds.contains(where: { $0.lowercased().contains(needle) }) { return true }
        return false
    }
}
