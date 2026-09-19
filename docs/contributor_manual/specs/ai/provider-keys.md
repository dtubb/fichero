# Provider API Keys — Design Spec (#TBD)

> Milestone: provider-keys
> Manual: TBD — the user manual's Settings section needs "Provider API keys": enter once,
> it keeps working across restarts; Test Connection only shows a green check when the app
> actually verified the key with the provider.

> Design-led (Testing Constitution). Creative director owns intent; tests enforce it; code
> makes them pass. **Status: DRAFT — awaiting approval.** Written from a field report (two
> verified bugs, #4815 and #4816) that exposed this surface had no spec behind it.
> Tags: **[OK]** built and tested · **[PARTIAL]** built, unproven or partly wired ·
> **[GAP]** intended, never built (needs an issue) · **[BROKEN]** regression, code
> contradicts the intent (needs an issue).

## Intent (the design)

A researcher enters a provider's API key once, in Settings, and it keeps working across
every future launch — a restart never quietly reverts to an old or deleted key. Removing a
key removes it, permanently, not until the next relaunch. There is exactly ONE place a local
engine's keys live; a remote engine's keys are that host's own business, never the app's. And
the app never claims a key works unless it actually checked: a "connection valid" green check
means a real probe answered, never "some non-empty string was present."

## Why this spec exists

A field report surfaced two verified defects with no spec behind either of them:

- **#4815** — every app launch re-pushes a stale, once-migrated copy of a provider's key to
  the engine, silently undoing a Settings save or a Settings remove. A whole afternoon of
  OpenRouter `401`s traced to exactly this: the key was fixed by hand in Settings, worked for
  70 consecutive calls, then the next launch resurrected the old, broken key.
- **#4816** — Test Connection reports success for any provider with no real probe wired
  (OpenRouter among them) the moment the key field is non-empty, regardless of whether the
  key is valid. A user who followed the app's own "Update API key in Settings" advice, then
  ran Test Connection and saw a green check, had no way to know the check meant nothing.

Both share one root cause worth naming once: a claim ("this key is saved", "this connection
works") that nothing in the code actually verifies.

## Two stores of truth (the shape of #4815)

- **App-owned Keychain** (`ProviderKeyStore.swift`, service `app.fichero.fichero.provider-keys`)
  — written exactly once, by a one-time migration off the engine's legacy keychain item
  (`migrateFromLegacyIfNeeded`); after that, `.alreadyOwned` forever. Pushed to the engine on
  EVERY connect (`EngineLifecycleController+ProviderKeys.swift`).
- **Settings' own path** (`ProvidersView+ProviderDetailView.swift`'s `saveAPIKey`/
  `removeAPIKey`) never touches the app-owned Keychain at all — it only calls the HTTP
  `providerService.setAPIKey`/`deleteAPIKey`, which reach the engine's OWN legacy keychain
  copy and its in-memory supplied-keys dict, never `ProviderKeyStore`.

So a Settings save/remove changes the engine's copy for the rest of that session, and the
next launch's connect sequence re-pushes whatever the app-owned Keychain item still holds —
the value from the original migration, unaffected by anything Settings has done since.

## Behaviors

### Persistence (#4815)

- `keys.one-store-of-truth` — **[OK]** (101a67cde, #4815 closed) a local engine's key lives in
  exactly one place the app treats as authoritative (the app Keychain). Before the fix there
  were two: the app-owned Keychain item (written once, at migration) and the engine's own
  legacy Keychain item + in-memory supply (written by every Settings save/remove and
  re-supplied on every connect) — `grep ProviderKeyStore fichero/fichero` found only the three
  launch-push call sites and the migration itself; `store`/`remove` had no production caller
  from Settings. Pinned:
  `ProviderAPIServiceKeyPersistenceTests.testSetAPIKeySuccessStoresTheTrimmedKey`,
  `::testSetAndDeleteAPIKeySkipTheKeychainForARemoteEngine`,
  `::testSupplyAPIKeyToEngineBodyNeverReferencesTheKeychainClosures`,
  `::testSupplyAPIKeyToEngineHasExactlyOneCaller` (all 4 read in full and confirmed to assert
  exactly this — `fichero/Tests/Unit/general/Services/ProviderAPIServiceKeyPersistenceTests.swift`).
- `keys.settings-save-survives-relaunch` — **[OK]** (101a67cde, #4815 closed) saving a new key
  in Settings stays in effect after the next launch. Pinned:
  `ProviderAPIServiceKeyPersistenceTests.testSetAPIKeySuccessStoresTheTrimmedKey`,
  `::testStaleKeyRegression_settingsSaveIsReflectedByTheNextEngineSupply` (the regression test
  named in the issue itself: a stale key seeded, a new one saved, the launch push's own
  read-then-supply shape reads back the NEW value, never the stale one),
  `::testSetAPIKeySuccessButKeychainFailureThrowsDistinctErrorWithNoKeyMaterial`. Honest gap:
  the suite cannot re-read the WIRE body to independently confirm the engine received the
  trimmed value byte-for-byte — the generated client sends this POST as an upload task, whose
  body a `URLProtocol` stub cannot see (the same limitation `BatchServiceTests.swift` already
  documents). What IS proven: `setAPIKey`
  computes ONE `trimmed` local and passes that SAME value to both the engine call and the
  Keychain closure (a source contract, `testSetAPIKeyTrimsOnceForBothTheEngineAndTheKeychain`)
  plus the closure receiving the expected trimmed string dynamically — the closest honest
  proof available without the wire-body seam.
- `keys.remove-survives-relaunch` — **[OK]** (101a67cde, #4815 closed) removing a key in
  Settings stays removed after the next launch. Pinned:
  `ProviderAPIServiceKeyPersistenceTests.testDeleteAPIKeySuccessRemovesTheKeyAndLeavesNothingForTheNextLaunchPush`.
- `keys.launch-supplies-to-engine` — **[PARTIAL]** (#4819, implemented, unpinned) the app supplies
  every candidate provider's app-owned key to the engine on every connect
  (`EngineLifecycleController+ProviderKeys.swift:27-66`,
  `supplyProviderKeysToEngine()`) — this mechanism is real and IS what makes the launch-push
  problem above visible (it works correctly, from a stale source). No Swift test exercises
  `supplyProviderKeysToEngine()` directly; `ProviderKeyStoreTests.swift` only covers the
  underlying `ProviderKeyStore` primitives it calls, not the connect-time supply loop itself.
- `keys.remote-engine-not-app-business` — **[PARTIAL]** (#4820, implemented, unpinned) a remote
  engine's provider keys are that host's own configuration; the app must never push its local
  Keychain keys to one. `supplyProviderKeysToEngine()` guards this explicitly
  (`guard !EngineConfig.engineProvisioningStrategy().connectsToRemoteHost else { return }`,
  `EngineLifecycleController+ProviderKeys.swift:28-31`) — real code, but no test asserts the
  guard actually short-circuits for a remote-configured engine.

### Verification (#4816)

- `keys.test-connection-real-probe` — **[OK]** (bca344581 app half; 35c4b53f1 + 5a9676909
  engine; #4816 closed) Test Connection only reports success when the app made a real network
  call to the provider and the provider confirmed the key, and a wrong/rate-limited/down
  endpoint never reads as a bad key. Provider breakdown (engine side): **real probes** —
  `apple_vision`, `apple_intelligence` (system checks), `ollama`, `lmstudio` (server
  reachability, no key involved), `openai`, `huggingface`, `google`, `groq`, `deepl` (the five
  original probes, now applying the same "only 401/403 means a bad key" rule), plus NINE
  added: `openrouter`, `anthropic` (a real authenticated request, no longer prefix-only),
  `mistral`, `together`, `deepseek`, `xai`, `perplexity`, `fireworks`, `cohere`. **Still
  unverifiable from here**: `azure`, `bedrock`, `dashscope` — these report a distinct "saved,
  could not verify" state rather than a false green check. The rule throughout: only a
  `401`/`403` (or a provider's own documented bad-key status — Google's `400`, kept as its
  real signal) means the key is bad; any OTHER non-2xx status means "could not verify," never
  "invalid." On the app side, `KeyTestOutcome.from(success:verified:)` is the pure derivation
  (read `KeyTestOutcomeTests.swift` in full — exhaustive over all 6 `(success, verified)`
  combinations, including a `nil` `verified` from an engine with no opinion yet correctly
  landing on "saved, not verified," never a positive claim) that
  `ProvidersView+ProviderDetailView.swift` now renders from instead of `result.success` alone.
  Pinned:
  `test_routes_provider_keys.py::test_connection_test_real_probe_success_sets_verified`,
  `::test_connection_test_real_probe_401_fails_unverified`,
  `::test_connection_test_real_probe_network_failure_reports_connectivity`,
  `::test_connection_test_real_probe_non_auth_status_is_unverified_not_failed`,
  `::test_connection_test_key_never_appears_in_response_or_logs`,
  `KeyTestOutcomeTests.testSuccessAndVerifiedTrueIsVerified`,
  `.testSuccessAndVerifiedFalseIsSavedNotVerified`,
  `.testSuccessAndVerifiedNilIsSavedNotVerified`,
  `.testFailureAndVerifiedTrueIsStillFailed`,
  `.testFailureAndVerifiedFalseIsFailed`, `.testFailureAndVerifiedNilIsFailed`.
- `keys.untested-provider-reports-not-verified` — **[OK]** (bca344581, #4816 closed) an
  untested provider reports a distinct "not verified" state and renders as neutral, never a
  green check — built on both sides now: the engine emits `ConnectionTestResponse.verified:
  bool | None` as a third state distinct from `success`
  (`test_connection_test_untested_provider_reports_saved_not_verified`, "Key saved — this
  provider cannot be verified from here", `azure`/`bedrock`/`dashscope`); the app derives
  `KeyTestOutcome` from the pair rather than keying its icon on `result.success` alone. Pinned:
  `test_routes_provider_keys.py::test_connection_test_untested_provider_reports_saved_not_verified`,
  `KeyTestOutcomeTests.testSavedNotVerifiedTintIsNeverGreen`,
  `.testVerifiedTintIsGreenAndFailedTintIsRed`, `.testEachOutcomeHasADistinctIcon`,
  `.testProviderDetailViewDoesNotKeyTheTestIconOnSuccessAlone` (a source-scan guarding the
  regression directly: the old binary `result.success ? "checkmark..." : "xmark..."` ternary
  must never come back). **What remains, honestly:** the PROVIDER LIST row's own status dot
  (`ProviderSettingsRow`) is unaffected by any of this — it is stateless and never sees a Test
  Connection result at all, still `isLocalProvider || provider.hasApiKey ? .green : .orange`
  (verified in code today). That gap belongs to `ai/ai-settings.md`'s local-runtime honest
  status behavior on the ai-settings milestone, a different behavior, unchanged by this fix.

### Apple Vision as an OCR/vision capability

- `keys.apple-vision-is-a-capability-not-only-a-key-check` — **[GAP]** (#2060, redirected
  from the legacy "Importer" milestone while folding `importer.md`'s pass 2) `apple_vision` is
  already a recognized provider with a real connection probe
  (`keys.test-connection-real-probe` above), but this issue's actual ask is broader: using
  Apple's Vision framework as an on-device OCR/vision ENGINE the importer or a workflow can
  choose, alongside cloud OCR providers — not only a settings-row key check. Whether Vision is
  wired as a selectable OCR/transcription engine anywhere in the import or workflow path was
  not verified this pass; the provider-key surface and the actual capability are two different
  questions, and this behavior is the capability one.

- `keys.key-never-in-logs` — **[PARTIAL]** (#4821) the app-supplied in-process key is never logged:
  `supply_api_key` (`fichero-server/src/fichero_server/security/provider_keys.py:39-58`)
  logs only the provider name and the fact of supply, explicitly documented ("Never log the
  key") and pinned by
  `test_supplied_provider_keys.py::test_the_key_is_never_logged`. The two other paths that
  touch a key value — `set_provider_api_key_impl`'s route-level logging
  (`api/routes/ai/provider_keys.py:114,120`, logs only the provider name) and
  `keychain.py`'s `set_api_key`/`delete_api_key` debug/warning lines (`keychain.py:266-299`,
  also provider-name-only) — were read and confirmed to never log the key value either, but
  neither has a dedicated test guarding it, hence PARTIAL rather than a blanket OK. A second
  pin lands with the Test Connection probe work: `test_routes_provider_keys.py::test_connection_test_key_never_appears_in_response_or_logs`
  (a sentinel key never appears in the response body, its JSON serialization, or the log
  capture, across a real probe path).
- `keys.argv-exposure` — **[GAP]** (#4818) `keychain.py:253-265` passes the plaintext key as
  `-w <key>` in argv to `/usr/bin/security add-generic-password`, visible to any other
  process on the machine (e.g. `ps`) for the subprocess's brief lifetime. Needs a design
  decision (stdin-based write, or a non-shelling-out primitive) before it can be fixed.

### Mid-run correctness

- `keys.per-call-key-resolution` — **[OK]** a workflow already in progress must pick up a
  key change without a process restart. `llm.get_api_key(provider)`
  (`fichero-server/src/fichero_server/llm/__init__.py:1222-1246`) resolves per call through a
  process-level cache that both the Keychain write path (`keychain.py`'s
  `_invalidate_llm_api_key_cache`) and the app-supplied path
  (`provider_keys.py`'s `_invalidate_llm_cache`) bust on every write/supply/forget. Pinned:
  `test_llm_api_key_cache.py::TestKeychainWriteInvalidatesCache::test_set_api_key_invalidates_cache`,
  `::test_delete_api_key_invalidates_cache`,
  `test_supplied_provider_keys.py::test_supplying_a_key_busts_the_resolution_cache`.

## Test matrix

| Leg | This surface? | Pins | File |
|-----|---------------|------|------|
| Pure rule (Swift) | y | `ProviderKeyStore` primitives (store/read/remove/trim/migrate) | `fichero/Tests/Unit/general/Services/ProviderKeyStoreTests.swift` |
| Availability (Swift) | y | `supplyProviderKeysToEngine()` pushes the CURRENT app-owned key, including after a Settings save/remove; remote-engine guard short-circuits | proposed, no file yet — the #4815 regression test |
| Backend (pytest) | y | per-call key resolution + cache invalidation on write/supply/forget | `fichero-server/tests/unit/security/test_llm_api_key_cache.py`, `test_supplied_provider_keys.py` |
| Backend (pytest) | y | `/test` returns a real probe result per provider, `not_verified` for the rest | `fichero-server/tests/unit/api/test_provider_keys.py` (proposed, no file yet found) |
| Click-around (XCUITest) | n | this is a Settings + engine-connect contract, not a full-app flow worth a dedicated UI test yet | — |

Hard-gate: `keys.settings-save-survives-relaunch`, `keys.remove-survives-relaunch`,
`keys.test-connection-real-probe` — these three are exactly what the field report broke.

## Open questions

1. Does the app-side fix (`saveAPIKey`/`removeAPIKey` also writing/removing
   `ProviderKeyStore`) fully retire the engine's own legacy-keychain write path
   (`provider_keys.py:143-148`'s own docstring already says the app-supplied POST should be
   memory-only), or does that engine-side cleanup wait for a separate pass?
2. `keys.untested-provider-reports-not-verified`: does "not verified" ever get its own real
   probe over time (starting with OpenRouter, per #4816's fix), or does the provider list
   grow faster than probes can be written, making "not verified" a permanent honest floor for
   most entries?
3. Should `anthropic`'s format-only check be reclassified as "not verified" too, since it
   makes no network call, or does prefix-validity count as a legitimate lightweight probe
   distinct from the `else` branch's true no-check?
4. `keys.argv-exposure` (#4818): stdin-based `security` invocation, or move off shelling out
   to `/usr/bin/security` entirely in favor of a Swift-side write only (the app already owns
   `SecItem` calls directly in `ProviderKeyStore.swift`) — does the engine need to write a
   keychain item at all once #4815 lands, or does #4815's fix make the engine-side Keychain
   write dead code?
5. `keys.launch-supplies-to-engine`/`keys.remote-engine-not-app-business`: worth a dedicated
   Swift test now, or fold into the same regression test #4815 already calls for?

## Legacy milestone note

"Settings - Models & Providers" (#20) is the maintainer's own 55-row triage queue and was not
touched beyond moving #4815/#4816 off it. Of its other open issues, only **#484 "Wire:
Providers + API Keys"** is really about provider KEYS specifically (title search across the
milestone) — everything else on it is about models, embeddings, MLX, or the broader Settings
UI, not key persistence/verification. Flagged for the maintainer's fold-in decision, not
moved.
