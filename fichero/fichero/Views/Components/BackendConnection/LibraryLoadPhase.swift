import SwiftUI

// MARK: - Library content loading (#4372)

/// What the library content area is honestly doing right now.
///
/// "Connecting to the library" and "loading its documents" are DIFFERENT
/// states, and the pane used to render both strings at once — a "Loading
/// Documents…" headline over a "Connecting to library data" subtitle — while a
/// third spinner spun forever whenever the engine never answered. One phase,
/// one line.
enum LibraryLoadPhase: Equatable {
    /// Talking to a server we do not own yet — no documents have been asked for.
    case connecting
    /// The app is bringing up the engine it owns.
    case startingEngine
    /// Connected; the tree/collection fetch is in flight.
    case loadingDocuments
    /// A final answer: there is nothing here. The empty state, not a spinner.
    case empty
    /// A final answer with rows.
    case loaded
    /// Something failed. The error affordance, NEVER a spinner.
    case failed(message: String)

    /// The one short line shown beside the spinner. Nil for the states that
    /// have their own dedicated view (empty / loaded / failed).
    var message: String? {
        switch self {
        case .connecting: return "Connecting…"
        case .startingEngine: return "Starting server…"
        case .loadingDocuments: return "Loading documents…"
        case .empty, .loaded, .failed: return nil
        }
    }

    /// A spinner means "wait, this is coming". It is a lie in every other state.
    var showsSpinner: Bool { message != nil }

    /// Phase precedence: a failure outranks everything (a spinner over a dead
    /// engine is the #4372 bug), then the engine's own readiness, then the
    /// collection fetch, and only then the empty/loaded answer.
    ///
    /// - Parameters:
    ///   - enginePhase: the single connection-state source.
    ///   - ownership: decides "Starting engine…" vs "Connecting…".
    ///   - hasLoadedSuccessfully: a collection load has succeeded at least once.
    ///   - isFetching: a collection load is in flight.
    ///   - isEmpty: the loaded collection has no rows.
    ///   - engineDetail: the honest engine-failure sentence, supplied by
    ///     `ConnectionPresentation` so both surfaces read the same words.
    ///   - loadErrorMessage: a collection-level failure message, if any.
    static func resolve(
        enginePhase: EngineSession.Phase,
        ownership: ConnectionPresentation.EngineOwnership,
        hasLoadedSuccessfully: Bool,
        isFetching: Bool,
        isEmpty: Bool,
        engineDetail: String,
        loadErrorMessage: String?
    ) -> LibraryLoadPhase {
        switch enginePhase {
        case .portConflict, .authRejected, .unreachable, .failed:
            return .failed(message: engineDetail)
        case .setupNeeded:
            return .connecting
        case .starting:
            return ownership == .appManaged ? .startingEngine : .connecting
        case .ready:
            break
        }
        if let loadErrorMessage { return .failed(message: loadErrorMessage) }
        if isFetching || !hasLoadedSuccessfully { return .loadingDocuments }
        return isEmpty ? .empty : .loaded
    }
}
