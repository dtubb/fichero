# Kimi lane — Convert EngineConfig.swift to generated OpenAPI client (#2414)

## What changed

- Converted `PairingService` in `fichero/fichero/Services/EngineConfig.swift` from hand-rolled `URLSession`/`URLRequest` calls to the generated `FicheroAPIClient` operations:
  - `createPairingCode()` → `client.api.createPairingCodeApiPairCodePost`
  - `listDevices()` → `client.api.listDevicesApiPairDevicesGet`
  - `revokeDevice(id:)` → `client.api.revokeDeviceApiPairDevicesDeviceIdRevokePost`
  - `pairDeviceUnauthenticated(code:deviceName:)` → `client.api.pairDeviceApiPairPost` with `Components.Schemas.PairRequest`
- Removed hand-maintained response structs (`PairedDeviceListResponse`, `PairingStatusResponse`) and the custom `URLSession`/`JSONDecoder`/`JSONEncoder` plumbing.
- Kept the public pairing model structs (`PairingCodeRecord`, `PairedDeviceRecord`, `PairingExchangeResponse`) so callers in `ShareSettingsView` and `BackendSettingsRemoteAccessSection` did not change.
- Updated `AuthTokenMiddleware` to treat `/api/pair` as an unauthenticated path, matching the engine's `_UNAUTHENTICATED_PATHS`. This preserves the old `PairingService` behavior of never forwarding a local bootstrap token to a remote host during pairing.
- Added `testPairingServiceBuildsQRCodePayloadFromClientBaseURL()` to `EngineConfigTests.swift` to lock down `buildQRCodePayload` behavior after the internal `apiRoot` storage moved to `client.baseURL`.

## Notes

- No backend API changes were made, so the committed OpenAPI client did not need regenerating.
- `xcodebuild` was not run per the lane instructions; only `swiftlint` was run on the touched files (EngineConfig.swift, EngineConfigTests.swift, AuthTokenMiddleware.swift — the last is excluded by project lint config).
- The conversion keeps the pinned/authed transport semantics: owner-side pairing uses the default `FicheroClient` (configured session + auth middleware); remote-client pairing uses the `expectedSPKIPin` initializer (pinned session + auth middleware, with `/api/pair` skipped by the middleware).
