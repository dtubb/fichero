@testable import Fichero
import Foundation
import Testing

/// #3937: a healthy library that simply hasn't loaded yet was rendered as an
/// outage — "Backend Not Connected … make sure the server is running on port
/// 8765" — because `DocumentStore.isConnected` starts `false` and only flips
/// true after a load SUCCEEDS. On a cold launch the gate flips `.ready`, the
/// library mounts, and the very first frame accused a perfectly healthy engine
/// of being down, with dev advice about a port the user doesn't run.
///
/// The rule these lock: a store is only offline when something actually FAILED.
struct LibraryContentStateTests {

    // MARK: - Never-loaded is startup, not an outage

    @Test("a store that has never loaded is awaiting its first load, not offline")
    func neverLoadedStoreIsAwaitingFirstLoad() {
        // The exact initial DocumentStore state: isConnected false, error nil.
        #expect(LibraryView.isAwaitingFirstLoad(hasLoadedSuccessfully: false, error: nil))
        // …and it is emphatically NOT an outage — this is the #3937 regression.
        #expect(LibraryView.isEngineOutage(nil) == false)
    }

    @Test("a loaded store is no longer awaiting its first load")
    func loadedStoreIsNotAwaitingFirstLoad() {
        #expect(LibraryView.isAwaitingFirstLoad(hasLoadedSuccessfully: true, error: nil) == false)
    }

    /// The guard against "fixing" this by defaulting `isConnected = true`: a real
    /// failure must never be mistaken for startup, or the spinner would hide it
    /// forever. The error is what ends the awaiting-first-load state.
    @Test("a failed first load is a failure, not startup")
    func failedFirstLoadIsNotAwaitingFirstLoad() {
        let failure = URLError(.cannotConnectToHost)
        #expect(LibraryView.isAwaitingFirstLoad(hasLoadedSuccessfully: false, error: failure) == false)
    }

    // MARK: - A real transport failure IS an outage

    @Test("a real transport failure surfaces the outage pane")
    func transportFailuresAreOutages() {
        #expect(LibraryView.isEngineOutage(URLError(.cannotConnectToHost)))
        #expect(LibraryView.isEngineOutage(URLError(.timedOut)))
        #expect(LibraryView.isEngineOutage(URLError(.networkConnectionLost)))
        #expect(LibraryView.isEngineOutage(URLError(.notConnectedToInternet)))
    }

    /// A failure that isn't an unreachable engine keeps its own message via
    /// `errorState` rather than being relabelled as an outage — claiming the
    /// engine is unreachable when it answered and returned garbage is its own
    /// lying frame.
    @Test("a non-transport failure is not relabelled as an outage")
    func decodingFailureIsNotAnOutage() {
        struct Decoding: Error {}
        #expect(LibraryView.isEngineOutage(Decoding()) == false)
    }

    /// TLS/pin rejection has its own remedy (reset the certificate) and must not
    /// be flattened into "can't reach the engine" — the engine is reachable, the
    /// trust is wrong.
    @Test("a TLS pin failure is not an outage")
    func tlsPinFailureIsNotAnOutage() {
        let ssl = NSError(domain: NSOSStatusErrorDomain, code: -9807, userInfo: nil)
        let wrapped = NSError(
            domain: NSURLErrorDomain,
            code: URLError.secureConnectionFailed.rawValue,
            userInfo: [NSUnderlyingErrorKey: ssl]
        )
        #expect(LibraryView.isEngineOutage(wrapped) == false)
    }

    // MARK: - The two predicates never both claim the frame

    /// F6 (never a blank pane / never a silent failure) needs the branches to be
    /// mutually exclusive: whatever the store's state, at most one of "still
    /// starting" and "the engine is unreachable" can be true, so the chain always
    /// lands on exactly one screen.
    @Test("awaiting-first-load and outage are mutually exclusive across every state")
    func predicatesAreMutuallyExclusive() {
        let errors: [Error?] = [nil, URLError(.cannotConnectToHost), URLError(.badURL)]
        for hasLoaded in [true, false] {
            for error in errors {
                let awaiting = LibraryView.isAwaitingFirstLoad(hasLoadedSuccessfully: hasLoaded, error: error)
                let outage = LibraryView.isEngineOutage(error)
                #expect(!(awaiting && outage), "hasLoaded=\(hasLoaded) error=\(String(describing: error))")
            }
        }
    }
}
