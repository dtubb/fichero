import Foundation

extension Document {
    /// Non-optional file type string for sorting (empty string for nil)
    var sortableFileType: String {
        fileType?.rawValue ?? ""
    }

    /// **Header binding only. This does not order anything (#3322).**
    ///
    /// A `Table` column that can be clicked to sort must declare a
    /// `KeyPathComparator`, and on macOS that comparator is bridged to an
    /// AppKit sort descriptor resolved against the column — a descriptor the
    /// bridge cannot map back is the crash class from #4282. So the Date
    /// column needs a key path even though the ROW ORDER for
    /// `document_date` comes from the engine.
    ///
    /// It exists only to satisfy that bridge, and it is deliberately a poor
    /// sort key so that using it as one is visibly wrong rather than subtly
    /// wrong: undated documents all collapse onto a single value, and the
    /// precision tie-breaking and `created_at` fallback that
    /// `histdate.document_date_sort_key` applies are both absent. Ordering
    /// rows with this would look like it worked.
    ///
    /// `LibrarySortField.orderedForDisplay` is what prevents that, and
    /// `LibrarySortFieldServerOrderingTests` is what keeps it prevented.
    var dateHeaderSortKey: Int {
        dateJdn ?? Int.min
    }
}
