import SwiftUI

/// Constants for sidebar layout and styling.
/// Following Apple's pattern from Food Truck sample.
enum SidebarConstants {
    /// Minimum sidebar width.
    static let minimumWidth: CGFloat = 200

    /// Corner radius for rounded elements.
    static let cornerRadius: CGFloat = 6

    /// Maximum characters for item names.
    static let maxNameLength = 255
}

/// The ONE place a sidebar row's list insets are decided (#4096).
///
/// Three call sites each carried their own `EdgeInsets` literal, with nothing
/// forcing them to agree and no way to see them at once. Auditing them turned
/// out to be more interesting than "pick a winner":
///
/// - **Leading is not drift.** 8 → 12 → 16 is a consistent 4pt step, and each
///   step matches a real nesting level: a library disclosure group sits at the
///   sidebar's outer edge, its item rows one level in, an inline alert row one
///   level further. Flattening these to a single value would have destroyed
///   structure that is doing a job.
/// - **Trailing already agrees** at 8, unanimously.
/// - **Vertical does NOT agree**, and that is the real defect the issue's
///   "rows do not share a vertical rhythm" symptom points at. See `vertical`.
///
/// So this is not a single value but a single FUNCTION of depth. A new row site
/// picks the level it belongs to and cannot invent numbers — which is the point
/// of consolidating: making the divergence unwriteable, not merely fixing the
/// instances of it.
enum SidebarRowMetrics {
    /// How deep a row sits in the sidebar's own structure. Not the document
    /// tree's depth — nested folders indent via `DisclosureGroup`, which is
    /// SwiftUI's job, not this type's.
    enum Depth {
        /// A library's disclosure group — the sidebar's outermost row.
        case library
        /// A row inside a library: documents, searches, workflows.
        case libraryItem
        /// An inline alert or status row rendered beneath library content.
        case inlineNotice
    }

    /// Leading inset per depth. The 4pt step is the sidebar's indent unit.
    static func leading(_ depth: Depth) -> CGFloat {
        switch depth {
        case .library: 8
        case .libraryItem: 12
        case .inlineNotice: 16
        }
    }

    /// Unanimous across every call site before this type existed.
    static let trailing: CGFloat = 8

    /// Vertical inset per depth — and the one genuine disagreement (#4476).
    ///
    /// `.libraryItem` returns 0 while the others return 2, because that is what
    /// the three sites did. It is preserved rather than harmonised so this
    /// consolidation renders IDENTICALLY to what shipped: a refactor that also
    /// restyles the sidebar cannot be reviewed, and cannot be reverted
    /// separately if the restyle is wrong.
    ///
    /// It is very likely wrong. `SidebarItemRow` adds `.padding(.vertical, 1)`
    /// to its own content, so an item row reaches roughly the same total height
    /// as a library row by a DIFFERENT mechanism — two ways of spelling one
    /// intention, which is how they drifted apart in the first place. Resolving
    /// it changes pixels and therefore needs eyes; filed as its own issue.
    static func vertical(_ depth: Depth) -> CGFloat {
        switch depth {
        case .libraryItem: 0
        case .library, .inlineNotice: 2
        }
    }

    /// The insets a sidebar row applies via `.listRowInsets`.
    static func insets(_ depth: Depth) -> EdgeInsets {
        EdgeInsets(
            top: vertical(depth),
            leading: leading(depth),
            bottom: vertical(depth),
            trailing: trailing
        )
    }

    /// All-zero insets for an INVISIBLE zero-height slot (the deferred
    /// disclosure placeholder that keeps a chevron rendered, #3355) — not a
    /// row style. Named here so no row site spells `EdgeInsets()` itself and
    /// the #4096 no-literal sweep stays enforceable.
    static let hiddenSlot = EdgeInsets()
}
