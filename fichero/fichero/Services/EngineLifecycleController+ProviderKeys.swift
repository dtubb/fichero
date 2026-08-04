import Foundation
import OSLog

// Split out of EngineLifecycleController.swift by file_length (#4534) — the
// same reason LibraryWindow+Actions.swift exists. The controller keeps the
// connect/spawn state machine; the provider-key supply that hangs off its
// success path lives here.
extension EngineLifecycleController {

    /// Hand the engine every provider key this app owns (#4534).
    ///
    /// Migration runs first and at most once per provider: a key the engine
    /// wrote before ownership moved is read once — with the user's Allow, per
    /// the documented ACL prompt — and re-stored under app ownership, so
    /// Daniel never retypes it. The legacy item is never deleted.
    ///
    /// NOT for a remote engine. A provider key that bills to this user's
    /// accounts must not come to rest in another host's process memory; a
    /// remote engine is configured with its own keys server-side. Same rule as
    /// "a remote connection cannot create a library" — the precondition the
    /// connection cannot satisfy makes the action wrong, not merely awkward.
    ///
    /// A failure to supply one provider never blocks the others, and never
    /// blocks the connect: it is logged, and the engine reports `not_supplied`
    /// with its remedy, which is the honest outcome rather than a dead app.
    func supplyProviderKeysToEngine() async {
        guard !EngineConfig.engineProvisioningStrategy().connectsToRemoteHost else {
            logger.info("Remote engine — provider keys stay local; the host holds its own (#4534)")
            return
        }

        var supplied = 0
        for provider in ProviderKeyStore.candidateProviders {
            switch ProviderKeyStore.migrateFromLegacyIfNeeded(provider: provider) {
            case .migrated:
                logger.info("Adopted engine-written key for \(provider, privacy: .public) (#4534)")
            case .refused(let status):
                // The engine used to call this "no key". It is not.
                logger.warning(
                    """
                    Key for \(provider, privacy: .public) exists but this app could not read it \
                    (OSStatus \(status)); engine will report it as not supplied
                    """
                )
            case .storeFailed:
                logger.error("Read the legacy key for \(provider, privacy: .public) but could not store it")
            case .alreadyOwned, .noLegacyItem:
                break
            }

            guard let key = ProviderKeyStore.key(for: provider) else { continue }
            do {
                try await appState.providerService.setAPIKey(providerType: provider, apiKey: key)
                supplied += 1
            } catch {
                logger.error(
                    """
                    Could not supply the key for \(provider, privacy: .public): \
                    \(error.localizedDescription, privacy: .public)
                    """
                )
            }
        }
        logger.info("Supplied \(supplied) provider key(s) to the engine on connect (#4534)")
    }
}
