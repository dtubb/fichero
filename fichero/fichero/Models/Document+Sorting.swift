import Foundation

extension Document {
    /// Non-optional file type string for sorting (empty string for nil)
    var sortableFileType: String {
        fileType?.rawValue ?? ""
    }
}
