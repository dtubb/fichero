import FicheroAPIClient
import Foundation

extension EntityStore {
    // MARK: - External authority curation (#3757)

    /// Load the external-authority setting from the backend. Fails soft: on
    /// error the flag stays at its last value and the error is published for
    /// the view to surface.
    func loadAuthoritySettings() async {
        isLoadingAuthoritySettings = true
        authoritySettingsError = nil
        defer { isLoadingAuthoritySettings = false }
        do {
            externalAuthorityEnabled = try await kgCurationService.externalAuthorityEnabled()
        } catch {
            authoritySettingsError = "Couldn't load authority settings: \(error.localizedDescription)"
        }
    }

    /// Enable/disable external authority linking, then reflect the persisted
    /// value the backend returns. Throws so the calling view can surface a
    /// precise message; the observable flag is only advanced on success.
    func setExternalAuthorityEnabled(_ enabled: Bool) async throws {
        externalAuthorityEnabled = try await kgCurationService.setExternalAuthorityEnabled(enabled)
    }

    /// Refresh (fetch + cache) external-authority candidates matching `query`
    /// (#3757). The store is the only endpoint accessor; the link sheet reads
    /// the returned candidates. Throws so the view can surface the failure —
    /// notably a 403 when external authority linking is disabled.
    func refreshAuthorityCandidates(query: String, limit: Int = 10) async throws -> [AuthorityCandidate] {
        let data = try await entityService.refreshAuthoritySnapshots(query: query, limit: limit)
        return Self.parseAuthorityCandidates(data)
    }

    /// Parse the `{ items: [...], count }` authority envelope. The OpenAPI
    /// `items` schema is freeform, so parse defensively — an item missing the
    /// required authority / id / label is dropped. Pure + exposed for tests.
    static func parseAuthorityCandidates(_ data: Data) -> [AuthorityCandidate] {
        guard let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any],
              let items = obj["items"] as? [[String: Any]] else { return [] }
        return items.compactMap { item -> AuthorityCandidate? in
            guard let authority = item["authority"] as? String,
                  let authorityId = item["authority_id"] as? String,
                  let label = item["label"] as? String else { return nil }
            return AuthorityCandidate(
                authority: authority,
                authorityId: authorityId,
                label: label,
                description: item["description"] as? String,
                sourceURL: item["source_url"] as? String
            )
        }
    }

    /// Link `entityId` to a previously refreshed authority snapshot (#3757).
    /// Throws so the sheet can surface a precise message; a non-throwing call is
    /// success.
    func linkAuthority(entityId: String, authority: String, authorityId: String) async throws {
        _ = try await entityService.linkAuthority(
            entityId: entityId,
            authority: authority,
            authorityId: authorityId
        )
    }
}
