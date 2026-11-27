import Foundation

/// One row of a node config's folder picker: a folder and its depth in the
/// tree. The Collection node and the schema-driven Folder tool list the same
/// rows.
struct WorkflowFolderOption: Identifiable {
    let folder: Document
    let depth: Int

    var id: String { folder.id }

    var indentedName: String {
        String(repeating: "  ", count: depth) + folder.name
    }

    /// The folders among `documents` as an indented tree: Inbox first, then
    /// the other roots by name, each followed by its children. A folder id
    /// that appears twice in the list is one row, so the pickers' rows keep
    /// distinct ids.
    static func tree(from documents: [Document]) -> [WorkflowFolderOption] {
        var seen = Set<String>()
        let folders = documents
            .filter { $0.docType == .folder && seen.insert($0.id).inserted }
            .sorted { $0.name.finderOrder($1.name) }

        var children: [String: [Document]] = [:]
        for folder in folders {
            guard let parentId = folder.parentId, seen.contains(parentId) else { continue }
            children[parentId, default: []].append(folder)
        }

        let roots = folders.filter { $0.parentId == nil }
        var options: [WorkflowFolderOption] = []
        func list(_ folder: Document, depth: Int) {
            options.append(WorkflowFolderOption(folder: folder, depth: depth))
            for child in children[folder.id] ?? [] {
                list(child, depth: depth + 1)
            }
        }
        for root in roots.filter({ $0.name == "Inbox" }) + roots.filter({ $0.name != "Inbox" }) {
            list(root, depth: 0)
        }
        return options
    }
}
