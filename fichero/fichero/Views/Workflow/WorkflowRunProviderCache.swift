import Observation
import Foundation

@MainActor
@Observable
final class WorkflowRunProviderCache {
    static let shared = WorkflowRunProviderCache()

    private(set) var providers: [LLMProvider] = []
    private var loaded = false

    private init() {}

    func ensureLoaded(chatService: ChatService?) async {
        guard !loaded else { return }
        guard let chatService else { return }
        do {
            providers = try await chatService.listProviders()
            loaded = true
        } catch {
            // Non-fatal; keep menu usable with Default option.
        }
    }
}
