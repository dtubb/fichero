import Foundation

enum PaneFocus: Hashable {
    /// Segments (#4942), Activity (#6441) and Activity Graphs: a click in any claims command focus, so Split / Close act on it.
    case sidebar, content, preview, reading, chat, inspector, segments, activity, activityGraphs, models

    /// Where focus starts when a window opens (#5824): the sidebar, never a text field such as the reader's find field.
    static let launchDefault: PaneFocus = .sidebar

    /// The pane a window opens in: the sidebar; nil when it is hidden, because no other pane binds a focus value
    /// (`.content` names no view), so setting one would only drop focus to the first key view (#5824, review 202).
    static func launchFocus(sidebarHidden: Bool) -> PaneFocus? { sidebarHidden ? nil : launchDefault }

    /// Human name for the pane — VoiceOver announcements on pane moves.
    var paneTitle: String {
        switch self {
        case .sidebar: return "Projects"  // the sidebar pane is Projects (ruled 2026-10-10)
        case .content: return ItemsPane.name
        case .preview: return SourcePane.name
        case .reading: return "Reader"
        case .chat: return "Chat"
        case .inspector: return "Inspector"
        case .segments: return "Segments"
        case .activity: return "Activity"
        case .activityGraphs: return "Activity Graphs"
        case .models: return ModelsWindowModel.windowTitle
        }
    }

    /// The pane KIND a focused pane is, for Split / Close / New Tab on the focused pane; nil for the
    /// sidebar and the inspector, which are not leaves of the pane list.
    var paneKind: PaneKind? {
        switch self {
        case .content: .library
        case .preview: .preview
        case .reading: .reading
        case .chat: .chat
        case .segments: .segments
        case .activity: .activity
        case .activityGraphs: .activityGraphs
        case .models: .models
        case .sidebar, .inspector: nil
        }
    }
}
