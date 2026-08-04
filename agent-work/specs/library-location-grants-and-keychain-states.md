# C1 — library locations via user-chosen grants · D2 — Keychain tri-state

Status: **DESIGN — not implemented.** Engine edits are held pending the
manager's go-ahead (the engine hot-reloads under Daniel while he tests).

Every Apple-behaviour claim below is marked **DOCUMENTED** (quoted from
developer.apple.com via the Xcode MCP) or **EMPIRICAL** (observed here).

---

## C1 — libraries anywhere, granted only by a panel

Daniel's ruling: libraries must be creatable anywhere, and a grant is minted
only when the user chose the location in an open/save dialogue. The engine's
allowlist stays; grants extend it per-path. `main.py:950` already names
"security-scoped bookmark grants held by this engine process" as an allowed
mechanism, so the shape exists — what follows is why it does not currently
work, and what has to change.

### The finding that decides the design

**DOCUMENTED** — `CFURLCreateBookmarkData`, "Discussion":

> For an app-scoped bookmark, no sandboxed app other than the one that created
> the bookmark can obtain access to the file-system resource that the URL
> points to. Specifically, **a bookmark created with security scope fails to
> resolve if the caller does not have the same code signing identity as the
> caller that created the bookmark.**

`FolderAccessManager.mintBookmark` creates `.withSecurityScope` bookmarks and
`security_scoped_access.py` resolves them **in the engine** — a different
binary with a different code signing identity. So the transfer mechanism is
using the one bookmark flavour that is documented not to work across
processes. This is not a Dev-only problem; it is wrong in the Release/embedded
build too, and it has simply never been the thing that failed first.

**DOCUMENTED** — "Accessing files from the macOS App Sandbox · Share file
access between processes with URL bookmarks" is the mechanism that IS meant
for this:

> Create bookmark data from a URL using `bookmarkData(...)`, passing `[]` as
> the value for the options parameter. The bookmark Foundation creates refers
> to a security-scoped URL that grants access to the resource **to a process
> that resolves the bookmark**. Your app can pass that bookmark to another
> process, like a launch agent or an XPC service. […] The receiving process
> **automatically attempts to extend its sandbox** to include the bookmarked
> resource when it uses the security-scoped URL.

And **DOCUMENTED** — `withoutImplicitSecurityScope`:

> Bookmarks that you create without security scope automatically carry
> **implicit ephemeral security scope. This security scope is valid until
> reboot at the latest**, and confers access to the resource to any other
> process that resolves the bookmark.

### Design

Two bookmark flavours, for two different jobs. They are not interchangeable
and the current code conflates them.

| Job | Flavour | Lifetime |
|---|---|---|
| App remembers the user's choice across launches | `.withSecurityScope` (app-scoped) | persistent |
| App hands access to the engine process | plain `bookmarkData(options: [])` | until reboot |

1. User picks the location in `NSSavePanel`/`NSOpenPanel`. **Only this mints
   access.** No path from a header, a config file, or an API body may ever
   mint a grant — the engine's grant endpoint must keep taking bookmark DATA,
   never a bare path, precisely so a path alone cannot buy access.
2. The app stores the `.withSecurityScope` bookmark (as today) and
   `startAccessingSecurityScopedResource()` around use.
3. **On every engine start, and on every new grant**, the app re-mints a PLAIN
   bookmark from the live security-scoped URL and sends that to the engine.
   Re-minting every start is not belt-and-braces — the implicit scope expires
   at reboot, so a persisted transfer bookmark is guaranteed to go stale.
4. Engine resolves the plain bookmark, holds the URL for the process lifetime
   (`security_scoped_access.py` already does exactly this), and
   `_granted_roots()` picks it up. No allowlist widening.

### The two-axes check, and the Dev Local wrinkle

*App owns the process; library owns the connection.* The grant is a
**process** fact — it belongs to whoever spawned the engine — so it rides the
app→engine channel, not the per-library connection. Both existing carriers are
process-scoped and correct: the `FICHERO_LIBRARY_BOOKMARKS` env var at spawn,
and `POST /api/sandbox/security-scoped-access` for a live engine.

**Release / embedded (`.releaseEmbedded`)**: the app spawns the engine, so
both carriers work. This is the path the design above fixes — change
`mintBookmark`'s transfer copy from `.withSecurityScope` to `[]` and the
engine can actually resolve it.

**Dev Local (`.debugExternal`)**: **EMPIRICAL** — the engine is started by the
developer from a shell (`start_backend.sh`), so the app never spawns it and
the env-var carrier does not exist. The live grant endpoint still does. But
the deeper point is that this engine is **not sandboxed at all** — it is a
plain user process that can already read the whole home directory. It does not
need an extension; it needs the *allowlist* to stop refusing. Two honest
options:

- **(a)** The grant endpoint accepts a path-only grant *when the request is
  loopback + bootstrap-authenticated AND the engine is not sandboxed*. The app
  still only calls it after a real panel interaction, so the user-intent
  invariant holds; the bookmark is simply unnecessary where there is no
  sandbox to extend. Risk: the engine cannot verify the app's claim that a
  panel happened. Mitigated by loopback+bootstrap being owner-equivalent
  already, but it is a genuine widening of the trust model in Dev only.
- **(b)** Dev uses `FICHERO_LIBRARY_ALLOWED_ROOTS`, set by `start_backend.sh`.
  No code change, no trust change, but it is a developer-machine
  configuration, not a product behaviour — and it means Dev and Release take
  different paths, which is exactly how one of them rots.

**Recommendation: (a), gated on an explicit "engine is unsandboxed" check
rather than on build configuration**, so the two builds run the same code and
the difference is a runtime fact the engine can verify about itself. (b) as
the stop-gap if the manager wants zero trust-model movement before the demo.

### Remote (Daniel's new constraint)

**Create-library must be unavailable whenever the connection is remote.** A
panel picks a path on the CLIENT's disk; a remote engine cannot see it, so
"create a library here" is incoherent and would fail at the API with a
confusing error. Strategy cases that may create a library: local ones only
(`.releaseEmbedded`, `.debugExternal`). Not `.configuredRemote`, not
`.iosCompanion`. iOS follows from the same rule — it never runs a local
engine. The UI must disable the affordance and say why, rather than letting
the request leave.

---

## D2 — Keychain must have three states, not two

Root cause proven by the manager: the item exists, the CLI-launched engine is
not on its ACL, `security` exits 36, and `get_api_key` returns `None` for it.

**DOCUMENTED** — "Access Control Lists":

> When an app attempts to access a keychain item […] the system checks whether
> the calling app is among the entry's trusted apps. If so, the system grants
> access. **Otherwise, the system prompts the user for confirmation.**

**EMPIRICAL** — non-interactively (no UI session for the prompt), `security`
cannot prompt, so it fails with rc 36 instead. This is why it worked before
the reboot: the trust decision was live in the session, and the reboot ended
it.

**DOCUMENTED** — TN3137: file-based keychains use ACLs (`SecAccess`); the
data-protection keychain uses access groups and requires entitlements
authorized by a provisioning profile, which a CLI-launched Python process does
not have. So the fix is not "move to the modern keychain" — that path is
closed for the engine as it is packaged today.

### The defect

`keychain.py:92-102` — every failure that is not rc 44 falls through to
`return None`, after a `logger.debug` invisible at the default level. Three
distinct facts collapse into one answer:

| Reality | rc | Reported today |
|---|---|---|
| key present, readable | 0 | present ✅ |
| item genuinely absent | 44 | absent ✅ |
| item present, unreadable (ACL / locked) | 36 and others | **absent ❌ — a lie** |

`has_api_key()` is `get_api_key() is not None`, and it has **8+ callers**
(`providers.py:145,180,207,318,522`, `provider_keys.py:156`,
`chat.py:1323`), so the lie propagates everywhere — including
`/api/providers/{t}/api-key/status`, which answers `has_api_key: false,
keychain_available: true` when the truth is "a key exists and I cannot read
it".

### Planned change (HELD — engine edits hot-reload under Daniel)

1. `keychain.py`: add `KeychainUnreadableError` and
   `lookup_api_key(provider) -> KeychainLookup` returning an explicit
   `found | absent | unreadable` plus the rc and stderr detail.
2. `get_api_key()` keeps `str | None` for absent, but **raises**
   `KeychainUnreadableError` on the third state. Rule zero: never substitute a
   different value for the real one.
3. `has_api_key()` stays `bool` (True only for `found`) and gains a sibling
   `api_key_state()` for callers that must distinguish. Log at **warning**,
   never `debug` — a credential that silently vanishes is the loudest thing in
   the system, not the quietest.
4. **Sweep the class** — same shape in `list_providers()` (`:223-224` returns
   `[]` on any failure, so a locked keychain reads as "no providers") and in
   `delete_api_key()`'s bare boolean.
5. Endpoint: `ProviderKeyStatusResponse` gains `key_state` (enum, per the
   "closed set is an enum, never a bare str" rule) and `key_error`. **This is
   an OpenAPI change** → `sync_openapi_schema.sh` + regenerate + commit the
   Swift client. The app renders "your key exists but Fichero can't read it —
   authorize access" instead of "no key".
6. `set_api_key` durability: **UNRESOLVED, needs a decision.** `security
   add-generic-password` has `-T` to add a trusted application to the new
   item's ACL, and `-A` to allow all applications. `-A` is a real weakening
   (any process reads the key). `-T` needs a path to trust, and the engine's
   identity differs between Dev (the venv python) and Release (the embedded
   binary), so a hardcoded `-T` would be wrong in one of them. My
   recommendation is `-T` with the *running* executable resolved at write
   time, so whichever engine wrote the key can read it back — but this is a
   security-boundary choice and I am not making it unilaterally.

### What NOT to do

Do not have Daniel retype the key as the fix. Retyping succeeds — the write
path works — and then the next reboot loses it again, because the read path is
what is broken.
