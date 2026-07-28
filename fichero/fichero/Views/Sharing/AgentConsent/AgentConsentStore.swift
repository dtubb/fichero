import Foundation
import Observation

/// A pending "an agent / MCP client wants to connect" request (#1847).
///
/// the user's decision (2026-07-21): agent & MCP accounts get an **Xcode-style
/// consent prompt** — connecting raises a prompt; approving auto-provisions the
/// account; "don't ask again" remembers the decision **for the session only**,
/// so a relaunch re-prompts. This is the value that prompt is raised for.
struct AgentConsentRequest: Identifiable, Equatable {
    let id = UUID()
    /// Human-facing name shown in the prompt (e.g. "Claude Desktop", or a chat
    /// agent's account name). Also the key the session-scoped decision is
    /// remembered under.
    let clientName: String
    /// Optional one-line description of what the client is asking to do. When
    /// nil the sheet shows a sensible default sentence.
    let purpose: String?

    init(clientName: String, purpose: String? = nil) {
        self.clientName = clientName
        self.purpose = purpose
    }
}

/// Session-scoped consent broker for agent/MCP connection requests (#1847,
/// UI-only prototype — the engine wiring that calls `requestConsent` on a real
/// connection event comes later).
///
/// The remembered decisions live in memory ONLY. That is the whole mechanism
/// behind the approved "relaunch re-prompts" rule: there is nothing to persist
/// and nothing to expire — quitting the app forgets every session approval.
@MainActor
@Observable
final class AgentConsentStore {
    /// The request currently awaiting the user's decision, or nil. The host view
    /// presents `AgentConsentSheet` while this is non-nil.
    private(set) var pending: AgentConsentRequest?

    /// Decisions the user asked to remember this session, keyed by client name.
    /// `true` = auto-approve, `false` = auto-deny. In-memory only (see type doc).
    private var sessionDecisions: [String: Bool] = [:]

    private var continuation: CheckedContinuation<Bool, Never>?

    init() {}

    /// Ask the user whether `request`'s client may connect.
    ///
    /// - Returns the remembered decision immediately if one exists for this
    ///   session; otherwise presents the sheet and suspends until the user
    ///   decides. A second request while one is already pending is denied rather
    ///   than stacking sheets (ponytail: a queue only if overlapping connects
    ///   ever actually happen).
    func requestConsent(_ request: AgentConsentRequest) async -> Bool {
        if let remembered = sessionDecisions[request.clientName] {
            return remembered
        }
        guard pending == nil else { return false }
        return await withCheckedContinuation { continuation in
            self.continuation = continuation
            self.pending = request
        }
    }

    /// Resolve the pending request. When `remember` is set, the decision (approve
    /// OR deny) is recorded for the rest of the session so the same client is not
    /// asked again until relaunch.
    func resolve(approved: Bool, remember: Bool) {
        guard let request = pending else { return }
        if remember {
            sessionDecisions[request.clientName] = approved
        }
        pending = nil
        let continuation = self.continuation
        self.continuation = nil
        continuation?.resume(returning: approved)
    }

    /// Test/preview seam: the remembered decision for `clientName`, or nil if the
    /// user has not chosen "don't ask again" for it this session.
    func rememberedDecision(for clientName: String) -> Bool? {
        sessionDecisions[clientName]
    }
}
