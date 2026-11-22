import Foundation

/// The pages of the iPhone's item view, in order (`ios.item.pages`, #6947). More pages are added at the end.
enum ItemPage: Int, CaseIterable, Identifiable {
    case source, reader, segments, info

    var id: Int { rawValue }

    var title: String {
        switch self {
        case .source: "Source"
        case .reader: "Reader"
        case .segments: "Segments"
        case .info: "Info"
        }
    }

    /// "2 of 4": what VoiceOver says with the selected tab (`ios.item.voiceover-reaches-every-page`).
    var position: String { "\(rawValue + 1) of \(Self.allCases.count)" }

    /// The page after this one; nil on the last (a swipe there does nothing).
    var next: ItemPage? { Self(rawValue: rawValue + 1) }

    /// The page before this one; nil on the first.
    var previous: ItemPage? { Self(rawValue: rawValue - 1) }

    /// Whether a horizontal drag changes page on this page: not on Segments (the page owns its drags,
    /// `ios.item.segments-own-their-gestures`) and not while the Source picture is zoomed
    /// (`ios.item.zoom-wins-over-paging`).
    func swipePages(imageZoomed: Bool) -> Bool {
        switch self {
        case .segments: false
        case .source: !imageZoomed
        case .reader, .info: true
        }
    }
}
