import Foundation

enum WorkflowRunTarget: Hashable {
    case file(String)
    case folder(String)

    fileprivate func directFileIDs(from documents: [Document]) -> [String] {
        switch self {
        case let .file(id):
            documents.contains { $0.id == id } ? [id] : []
        case let .folder(path):
            documents
                .filter { $0.docType == .file && $0.parentId == path }
                .map(\.id)
        }
    }
}

/// Resolves the exact direct-file document scope for a context-menu workflow run.
enum WorkflowRunTargetResolver {
    static func resolve(
        clicked: WorkflowRunTarget,
        selection: Set<WorkflowRunTarget>,
        documents: [Document]
    ) -> [String] {
        let targets = selection.contains(clicked) ? Array(selection) : [clicked]
        let targetFileIDs = Set(targets.flatMap { target in
            target.directFileIDs(from: documents)
        })
        return documents.map(\.id).filter(targetFileIDs.contains)
    }
}
