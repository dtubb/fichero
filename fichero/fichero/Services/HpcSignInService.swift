import FicheroAPIClient
import Foundation
import Observation
import OpenAPIRuntime

/// Signs in to a Slurm cluster and answers what ssh asks on the way (`compute.connect.second-factor-passes-through`,
/// #5238). The engine runs ssh; its own prompt text (a Duo passcode, a key passphrase) comes out of
/// `GET /api/hpc/prompts` and the person's answer goes back with `POST /api/hpc/prompts/{id}`. Nothing is stored here.
@MainActor
@Observable
final class HpcSignInService {
    struct Prompt: Identifiable, Equatable {
        let id: String
        let text: String
    }

    enum Phase: Equatable {
        case idle
        case signingIn
        case signedIn
        case failed(String)
    }

    private let client: FicheroClient
    private(set) var prompts: [Prompt] = []
    private(set) var phase: Phase = .idle

    init(ficheroClient: FicheroClient) {
        self.client = ficheroClient
    }

    /// Opens the one connection. Returns when it is open or the attempt ended; while it runs, `prompts` is kept fresh.
    func signIn(clusterId: String) async {
        phase = .signingIn
        let poller = Task { [weak self] in
            while !Task.isCancelled {
                await self?.refreshPrompts()
                try? await Task.sleep(for: .milliseconds(700))
            }
        }
        defer {
            poller.cancel()
            prompts = []
        }
        do {
            let response = try await client.api.signInApiHpcClustersClusterIdSignInPost(path: .init(clusterId: clusterId))
            switch response {
            case .ok:
                phase = .signedIn
            case .undocumented(let status, _):
                phase = .failed(Self.words(forStatus: status))
            default:
                phase = .failed("The cluster would not sign you in.")
            }
        } catch {
            phase = .failed("Could not reach the engine to sign in: \(error.localizedDescription)")
        }
    }

    func refreshPrompts() async {
        guard let response = try? await client.api.listPromptsApiHpcPromptsGet(),
              case .ok(let ok) = response,
              let body = try? ok.body.json
        else { return }
        let fresh = body.items.map { Prompt(id: $0.id, text: $0.prompt) }
        if fresh != prompts { prompts = fresh }
    }

    /// Sends the answer on. A prompt that expired or was refused meanwhile (the engine answers 404/410) is said so,
    /// never swallowed: the sheet shows it and the person signs in again.
    func answer(_ prompt: Prompt, with text: String) async {
        do {
            let response = try await client.api.answerPromptApiHpcPromptsPromptIdPost(
                path: .init(promptId: prompt.id), body: .json(.init(answer: text)))
            if case .undocumented(let status, _) = response, status == 404 || status == 410 {
                phase = .failed(Self.words(forStatus: status))
            }
        } catch {
            phase = .failed("Could not send your answer to the engine: \(error.localizedDescription)")
        }
        await refreshPrompts()
    }

    /// The clusters set up in Settings, for the Clusters section.
    func listClusters() async -> [Cluster] {
        guard let response = try? await client.api.listClustersApiHpcClustersGet(),
              case .ok(let ok) = response, let body = try? ok.body.json
        else { return [] }
        return body.items.map { Cluster(id: $0.clusterId, name: $0.name, host: $0.hostAlias) }
    }

    struct Cluster: Identifiable, Equatable {
        let id: String
        let name: String
        let host: String
    }

    #if DEBUG
    /// Previews only: a service already in a state, without an engine.
    func showForPreview(prompts: [Prompt], phase: Phase) {
        self.prompts = prompts
        self.phase = phase
    }
    #endif

    /// The engine's refusals, said plainly (the sign-in route answers 409 with no key and 502 when ssh ended).
    private static func words(forStatus status: Int) -> String {
        switch status {
        case 409: return "This cluster has no key yet. Make one in Settings, add its public half in CCDB, then try again."
        case 502: return "The cluster ended the sign-in: the answer was wrong, refused or timed out."
        case 404, 410: return "That sign-in prompt has expired or was refused. Sign in again and answer within the time."
        default: return "Signing in failed (\(status))."
        }
    }
}
