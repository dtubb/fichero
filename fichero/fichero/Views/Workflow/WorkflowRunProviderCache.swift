import Foundation

@MainActor
final class WorkflowRunProviderCache: ObservableObject {
    static let shared = WorkflowRunProviderCache()

    @Published private(set) var providers: [LLMProvider] = []
    private var loaded = false

    private init() {}

    func ensureLoaded(chatService: ChatServiceGenerated?) async {
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
