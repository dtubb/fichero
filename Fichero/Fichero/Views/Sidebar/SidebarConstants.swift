import SwiftUI

/// Constants for sidebar layout and styling.
/// Following Apple's pattern from Food Truck sample.
enum SidebarConstants {
    // MARK: - Spacing

    /// Standard horizontal padding for sidebar items
    static let itemLeadingPadding: CGFloat = 4

    /// Vertical padding for section headers
    static let sectionHeaderVerticalPadding: CGFloat = 4

    /// Horizontal padding for section headers
    static let sectionHeaderHorizontalPadding: CGFloat = 8

    // MARK: - Sizing

    /// Minimum sidebar width
    static let minimumWidth: CGFloat = 200

    /// Corner radius for rounded elements
    static let cornerRadius: CGFloat = 6

    // MARK: - Drop Highlighting

    /// Opacity for drop targets (folders)
    static let dropTargetOpacity: CGFloat = 1.0

    /// Opacity for drop targets (non-folders)
    static let dropTargetNonFolderOpacity: CGFloat = 0.3

    /// Opacity for section header drop targets
    static let sectionDropTargetOpacity: CGFloat = 0.3

    // MARK: - Text Limits

    /// Maximum characters for item names
    static let maxNameLength = 255
}
