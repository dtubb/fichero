import Foundation

/// Where the next search looks (#6729): the page being read, its document, the browsed folder, the whole project
/// (this library) or everywhere. The engine takes one node id as its `folder_id` filter and expands it to that node
/// and everything under it, so Page, Document and Folder differ only in the id they send.
enum SearchScope: String, CaseIterable, Equatable {
    case page, document, folder, project, everywhere

    var title: String {
        switch self {
        case .page: "This Page"
        case .document: "This Document"
        case .folder: "This Folder"
        case .project: "This Project"
        case .everywhere: "Everywhere"
        }
    }

    /// The search field's placeholder: what the next search looks in.
    var placeholder: String {
        switch self {
        case .page: "Search this page"
        case .document: "Search this document"
        case .folder: "Search this folder"
        case .project: "Search this project"
        case .everywhere: "Search everywhere"
        }
    }
}
