import Combine
import FicheroAPIClient
import SwiftUI

// MARK: - LibraryView content branches (file-length split, 2026-08-13)
//
// The engine-failure / loading / rows-or-empty branch stack `body` hosts.

extension LibraryView {
    @ViewBuilder
    var libraryContent: some View {
        // #4372: a failed engine is an error affordance, never a spinner. This
        // branch has to come FIRST, because `isAwaitingFirstLoad` is true
        // whenever no load has succeeded AND no load has failed — which is
        // exactly the shape of "the engine never answered, so nothing was ever
        // asked for". Without it the pane spins forever over a dead engine.
        if let engineFailure = engineFailureDetail {
            connectionErrorState(message: engineFailure)
        } else if isCollectionLoading || isAwaitingFirstLoad {
            loadingState
        } else {
            libraryFailureOrRows
        }
    }

    /// The failure branches, split out of `libraryContent` so no single
    /// `@ViewBuilder` body carries seven branches plus a nested switch.
    ///
    /// Purely a factoring: the chain order is unchanged, so the precedence
    /// (access denial → engine outage → generic error → rows) is exactly what
    /// it was. `LibraryWindow.body` has a documented type-check-timeout history
    /// in this codebase and #4372 added a branch to this chain, so it is
    /// bounded now rather than after a failed build.
    @ViewBuilder
    private var libraryFailureOrRows: some View {
        if appState.engine.phase == .starting {
            // FIRST LAUNCH, engine still booting (Daniel's screenshot,
            // 2026-08-10 5:57pm): the pane showed "No Access to Local /
            // You're not signed in" while the toolbar said "Starting
            // engine…" — a stale AccessError from the pre-boot probe
            // rendered as if the running engine had denied us. While the
            // engine is STARTING there is nothing to be signed in to; show
            // the calm truth, and the phase change re-evaluates this branch
            // the moment the engine is up.
            VStack(spacing: 10) {
                ProgressView()
                    .controlSize(.small)
                Text("Starting engine…")
                    .font(.callout)
                    .foregroundStyle(.secondary)
            }
            .frame(maxWidth: .infinity, maxHeight: .infinity)
        } else if !isShowingEntitiesCollection, let denial = documentStore.error as? AccessError {
            // Never a silent 403 / blank pane (F6): a denied library read lands on
            // the explicit access state — which library, why, who you are, and the
            // next action — instead of the generic "couldn't load" text.
            LibraryAccessDeniedView(
                libraryName: libraryReference?.displayName ?? "this library",
                error: denial,
                libraryPath: libraryReference?.url.path,
                identity: appState.identityStore,
                onRetry: { onRetry() },
                onSignIn: nil,
                onResetPin: { RemoteCertificatePinning.clearPersistedSPKIPin(hostString: EngineConfig.hostString) }
            )
        } else if !isShowingEntitiesCollection, Self.isEngineOutage(documentStore.error) {
            connectionErrorState(message: engineUnreachableDetail)
        } else if let activeErrorMessage {
            errorState(message: activeErrorMessage)
        } else {
            libraryRowsOrEmptyState
        }
    }

    /// The final answer: rows, or the empty/placeholder state.
    @ViewBuilder
    private var libraryRowsOrEmptyState: some View {
        if isCollectionEmpty {
            // "Empty folder" and "contents not here yet" looked identical, so a
            // folder click or a drop showed "No Documents" and then relaid out
            // when the data landed (#4235). Show what is already in flight.
            let placeholder = emptyCollectionPlaceholder
            if placeholder == .empty {
                emptyState
            } else {
                contentPlaceholderState(placeholder)
            }
        } else {
            switch displayMode {
            case .icon:
                iconsView
            case .list:
                listView
            case .table:
                tableView
            case .columns:
                columnsView
            case .cards:
                datasetModeView(.cards)
            case .timeline:
                datasetModeView(.timeline)
            case .calendar:
                datasetModeView(.calendar)
            case .geoMap:
                datasetModeView(.map)
            case .canvas, .workspace:
                canvasModeView
            case .space:
                spaceModeView
            }
        }
    }

    /// "Live updates paused" pill (F7), shown only when this library's change
    /// stream has dropped. Reading `stream.liveUpdatesUnavailable` (a nested
    /// @Observable) makes the pill appear/disappear reactively.
    @ViewBuilder
    var liveUpdatesPausedInset: some View {
        if let ref = libraryReference {
            // Remote change delivery rides the activity stream (#3159/#2479), so
            // a 403 there means this device has no role on the library — a
            // terminal state with no reconnect (retrying can't mint access).
            if ref.changeStream.accessDenied || ref.activityStore.liveUpdatesAccessDenied {
                HStack {
                    Spacer(minLength: 0)
                    LiveUpdatesPausedPill(
                        message: "No access to live updates",
                        systemImage: "lock.slash",
                        onReconnect: nil
                    )
                    Spacer(minLength: 0)
                }
                .padding(.top, 8)
                .padding(.bottom, 4)
            } else if ref.changeStream.liveUpdatesUnavailable || ref.activityStore.liveUpdatesPaused {
                // Either the dedicated change stream (local) or the folded
                // activity stream (remote) dropped — say so instead of quietly
                // going stale, and offer a one-tap resubscribe of both.
                HStack {
                    Spacer(minLength: 0)
                    LiveUpdatesPausedPill(onReconnect: {
                        ref.changeStream.stop()
                        ref.changeStream.start()
                        ref.activityStore.reconnectLiveUpdates()
                    })
                    Spacer(minLength: 0)
                }
                .padding(.top, 8)
                .padding(.bottom, 4)
            }
        }
    }

    /// One dataset renderer as a FULL view mode (Daniel 2026-08-14), over
    /// the dataset query scoped to the browsed folder (recursive).
    /// Double-click resolves the row to its live Document and opens it.
    @ViewBuilder
    func datasetModeView(_ renderer: DatasetRenderer) -> some View {
        if let service = scopedLibraryReference?.documentService {
            DatasetModeView(
                renderer: renderer,
                folderId: folderId,
                documentService: service,
                entityService: scopedLibraryReference?.entityService,
                onOpen: { row in
                    Task { @MainActor in
                        if let document = try? await service.getDocument(row.id) {
                            openDocument(document)
                        }
                    }
                }
            )
        } else {
            ContentUnavailableView(
                "No Library",
                systemImage: "tray",
                description: Text("The Data view needs an open library.")
            )
        }
    }
}
