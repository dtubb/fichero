# Plan: sharing between Macs works in the next release (2026-10-17)

Spec: `docs/contributor_manual/specs/transport/library-sharing.md` (acceptance `sharing.two-macs-end-to-end`).
Checklist: `agent-work/status/SHARING-TWO-MAC-CHECKLIST.md`. Milestone: "Sharing & Pairing — Dead-Simple UX".
Rulings kept: loopback + `tailscale serve`; fail-closed; loopback = owner; accounts = people; QR/Bonjour/TLS pairing; two toggles; logic in the engine; generated client only.

## Two toggles, exact wording (Settings › Sharing)
- **Sharing** — headline On/Off; caption "Share Fichero on this Mac with other devices, the fichero command-line tool, and MCP clients." (as built)
- **Multi-user** — "Give other people their own accounts on this Mac's libraries." (today the switch is in Engine settings; move/duplicate beside Sharing, #3284)
Nothing else on the screen except the pairing card and the paired-devices list.

## Order of work
Defects first
1. **#5319** who-did-it (fix landed 6b6115612 per issue; verify on integration, re-tag `sharing.who-did-it` OK). Files: `fichero-server/.../api/routes/auth/pairing.py`, `security/authz.py`, `db/app.py` (audit device column). Test `unit/security/test_sharing_probe_2026_10_01.py`. Unit-testable.
2. **#4224** pairing transport (fix 734d16f56): prove in a Release-embedded build. `fichero/fichero/Services/PairingTypes.swift`, `EngineConfig+Launch.swift`. Swift unit + checklist step 1 (M4/this Mac).
3. **#5320 / #5311 / #5317** Tailscale: serve terminates TLS (c3dabd500); sandbox can't run the CLI? Files `security/tailscale_serve.py`, `remote_access_tls.py`, `RemoteAccessConfig.swift`. Engine tests exist (`test_tailscale_serve.py`); app-in-sandbox part needs M4 (step 15).
4. **#5348** stale edit: app must send `expected_updated_at`, show keep-mine/take-theirs/compare; add `PUT /api/documents/{id}` check. Engine `api/routes/document/*`, Swift note editor. Engine unit + checklist 12.
5. **#5314** change stream: fix landed; keep its test green.
Gaps the acceptance story needs
6. **#3284** one Multi-user source (+ move the switch beside Sharing). Files `fichero-server/.../security/multiuser.py`, `EngineSettingsView`, `RemoteAccessConfig.swift`. Engine unit (env precedence) + Swift.
7. **#2403 / #5735** B chooses and authenticates a person; names on edits. Files `security/accounts.py`, `api/routes/auth/auth.py`, `RemoteClientPairingFlow.swift`, a person picker in `MacRemoteClientPairingSection.swift`. Engine in-process 2-account test; picker needs M4 (steps 5, 9).
8. **#5734** Mac finds host (Network.framework browse of `_fichero._tcp`; typed `.local` fallback). `MacRemoteClientPairingSection.swift`, new `HostBrowser` Service; pure rule unit-testable, real discovery needs M4 (step 3).
9. **#5731** sharing off closes the guest: engine emits typed `sharing_stopped` on the change stream before closing the listener (`api/change_stream.py`, `__main__.py`); Swift shows one sentence + closes windows (`LibraryManager.swift`). Engine unit + checklist 16.
10. **#5732** remote run in host Activity (device on activity rows; `api/routes/system/activity.py`). Engine unit; live view step 10.
11. **#5733** undo after remote edit (undo-everywhere #5658; refusal sentence names who). Engine unit; windows step 11.
12. **#5351** revoke cascades: `db/app.py revoke_device` (add paired_by walk), `api/routes/auth/pairing.py` list "will also revoke", Swift revoke sheet. Engine unit; sheet step 14. Also confirm tailnet peers no longer look like loopback (step 15).
Nice to have
13. #3273 library confirmed on pair; #3335 ACL status wording; #2054 owner shared-libraries view; #2083 Accounts & Users screen (partly exists: `UsersContent+Layout.swift`); #3371/#3290 iOS (not in this release story).
Out of scope for this story: #4789/#4790/#5271 in-memory transport, #4560/#4561/#4570 startup, iOS substrate items, IIIF #5327, #2029 multi-writer.

## Testable without the M4
Everything engine-side: audit attribution, 2-account in-process pair + edit + stale 409 + revoke cascade + sharing-off event, activity row with device, undo refusal, env precedence for Multi-user. Name: `fichero-server/tests/unit/transport/test_*_to_spec.py` (new dir; each file cites `library-sharing` in its docstring). In-process e2e extends `test_device_pairing_e2e.py`.
## Needs the M4
Bonjour browse across machines, real certificate pin on a second Mac, Release-embedded UDS pairing, sandboxed Tailscale, Keychain, window closing on sharing-off, live Activity, per-window undo with B editing. All are checklist steps 1–17.

## Seen contradicting rulings / risks
- Spec header says DRAFT; `check_specs_have_tests` exempts it. When approved, every `*_to_spec.py` above must exist.
- #3284 premise moved: multiuser is explicit opt-in only (#3331); the remaining risk is an app-spawned engine with `FICHERO_MULTIUSER=0` while hosting.
- Pairing-over-tailnet and `engine_owner` for peers behind a raw TCP forward (#5351 half) must be re-checked now that serve terminates TLS.
