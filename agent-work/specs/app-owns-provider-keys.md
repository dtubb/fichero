# D2 phase 2 — the APP owns the provider key; the engine never reads a keychain

Status: **DESIGN — held for the manager's review. No source touched.**
Decided by Daniel: the app owns the keychain item; the engine receives the key
over the authenticated transport.

Claims are marked **DOCUMENTED** (developer.apple.com via the Xcode MCP) or
**EMPIRICAL** (measured here today).

---

## Why this is the right axis

**EMPIRICAL** — the failure was an identity mismatch, not a storage problem. The
item is fine; `security find-generic-password -s com.fichero.fichero -a
openrouter -w` exits 36 for the CLI-launched engine because the item's ACL does
not trust that binary.

**DOCUMENTED** — Access Control Lists: *"the system checks whether the calling
app is among the entry's trusted apps. If so, the system grants access.
**Otherwise, the system prompts the user for confirmation.**"* The engine is
never prompted because it has no UI session to prompt in, so the prompt becomes
a refusal.

So the durable question is *which identity holds the item*. The app is
code-signed, stable across reboots, and already the thing the user grants
permission to. The engine is a Python process whose executable path differs
between Dev (a venv interpreter) and Release (an embedded binary) and moves
whenever it is rebuilt. **An ACL can only be as stable as the identity it
names.**

**The mechanism already exists in the app** — this is wiring, not new
capability. `fichero-api-client/Sources/FicheroAPIClient/AuthTokenMiddleware.swift`
already does `SecItemCopyMatching`/`SecItemAdd` against
`app.fichero.fichero.session-token` and `app.fichero.fichero.remote-device-token`,
keyed per host. Provider keys become a third service on that same helper. No new
keychain code, no second pattern.

---

## 1. Migrating the key that already exists

There is a live item: service `com.fichero.fichero`, account `openrouter`,
written 2026-07-27. Daniel must not retype it and must not lose it.

**DOCUMENTED** — per the ACL text above, a non-trusted caller with a UI session
gets a *user-confirmation prompt*, not a hard failure, and *"the user may choose
to Deny, Allow, or Always Allow… In the latter case, the system adds the app to
the list of trusted apps for that entry."* The app has a UI session. So the app
can read the legacy item once, with Daniel clicking Allow.

**EMPIRICAL — NOT YET VERIFIED, and it is the load-bearing unknown.** I have
confirmed the engine is refused; I have **not** confirmed the app is prompted
rather than refused for this specific item, because verifying it means running
the app, which I am not permitted to do. **The migration must be built to
survive that verification failing.**

Migration, one-way and non-destructive:

1. On launch, if `app.fichero.fichero.provider-keys/<provider>` is absent and a
   legacy `com.fichero.fichero/<provider>` item exists, attempt one read.
2. Success → write it under app ownership. **Leave the legacy item in place**;
   do not delete it. Deleting is the only irreversible step here and it buys
   nothing. A later cleanup can remove it once the new path is proven.
3. Refused/failed → do **not** report "no key". Surface the third state the
   engine already models (`unreadable`) with the real reason, and offer the
   entry field. This is the whole point of `1b11eddd7`: the failure has
   somewhere honest to land.
4. Never silently drop the legacy item, and never migrate without the user's
   own Allow — the prompt IS the consent.

---

## 2. Where the key lives engine-side, and for how long

**In memory, process lifetime only. Never persisted.**

Persisting it engine-side re-creates the problem in a new place: a second copy
with a second lifetime, a second thing to go stale, and a second answer to
"where is my key". The engine already has the right seam — `llm/__init__.py`
resolves keys through a process-level cache with `clear_api_key_cache(provider)`
(#2545). App-supplied keys become that cache's source of truth, and
`POST /api/providers/{type}/api-key` stops writing a keychain and instead
populates it.

Consequence, stated plainly: **an engine restart loses the keys until an app
re-supplies them.** That is correct, not a regression to paper over — it is what
"the app owns it" means. It must be *visible* (see §3), never silent.

Ordering follows the existing spawn/live pattern in `EngineLifecycleController`:
supply keys once the engine is ready, and re-supply on reconnect.

---

## 3. When the engine runs and no app has supplied a key

This is where the governing rule bites hardest, because it is the case that
*used* to fail silently.

Reachable in five ways: the embedded engine outliving its last window; a
CLI invocation; an MCP tool call; a headless run; a cron/schedule trigger.

Required behaviour: **fail explicitly, naming the state.** Not "provider
unavailable", not a skipped node, not a fallback to a different provider. The
error must say: this provider needs a key, no app session has supplied one, and
here is how to supply it (open Fichero, or configure a server-side key per §4).

The engine already has the vocabulary for this after `1b11eddd7` — the third
state generalises from "keychain refused me" to "nobody has given me this key",
which is the same fact from the caller's side: *the key is not obtainable, and
that is different from not existing*. `key_state` should gain a
`not_supplied` member rather than reusing `absent`, because a user with a
perfectly good key in the app must never be told there is no key.

**Environment variables stay a legitimate source** (`OPENAI_API_KEY` and
friends), which is what makes headless and CI runs viable at all. The existing
fallback in `_read_api_key_uncached` already logs why it was taken.

---

## 4. The remote-engine case

**Honest answer: a remote engine holds its own keys, configured server-side. The
app does not ship provider keys over the wire to a remote host.**

Sending them would mean a credential that bills to Daniel's accounts leaving his
machine and coming to rest in another host's process memory, where its lifetime
and exposure are governed by that host, not by him. The transport is
authenticated and TLS-pinned, so this is not about interception — it is about
where the secret ends up living and who can be asked to delete it. "The app owns
the key" and "the app hands the key to someone else's machine" are not the same
policy.

So: local engines (embedded, and the external dev engine while it exists) get
keys from the app. Remote engines are configured with their own, and the app's
provider UI should say so for a remote connection rather than offering a field
that silently does nothing. This mirrors the C1 rule that a remote connection
cannot create a library — same shape: **an affordance whose precondition the
connection cannot satisfy must be visibly unavailable, not fail at the API.**

---

## 5. CLI and MCP

**EMPIRICAL** — neither reaches the keychain: `grep get_api_key` over
`fichero-cli/src` and `fichero-mcp/src` returns nothing. Both are thin HTTP
clients, per AGENTS.md.

So they are unaffected *directly* and affected *entirely* in practice: a CLI
workflow run needs the engine to have a key, and under this design that means an
app has supplied one or an env var is set. That is exactly the §3 case, and it
is why §3's error must be explicit — a CLI user seeing "provider unavailable"
has no way to guess that the answer is "open the app once".

---

## 6. Dependency on which engine modes survive

**Flagged per the manager's note.** Daniel is separately asking whether the
developer-run external engine mode should exist at all.

This design has a real dependency on that answer, and it is a simplifying one:

- **Embedded** — the app spawns it, so key supply is trivially ordered.
- **Remote** — §4, server-side keys.
- **External dev engine** — the *only* mode where a long-lived engine has no
  owning app, and therefore the only mode that makes §3's "no app has supplied a
  key" a routine state rather than an edge case.

**If the external dev mode goes away, this design gets materially simpler**: every
local engine has an owning app by construction. If it stays, §3 is load-bearing
and needs its own test coverage. I am not arguing for either — but the coupling
is real and Daniel should see it before deciding.

The same is true of C1: the external engine is the mode where the
security-scoped-bookmark transfer has no sandbox to extend and needed a
special case.

---

## 7. Tests

Per state: readable / absent / unreadable / not-supplied. Per transition:
legacy-item present + app can read → migrated, legacy left intact;
legacy present + app refused → surfaces `unreadable` with the real reason, entry
field offered, **nothing deleted**; no legacy item → clean first-run;
already-migrated → no prompt, no second read. Plus: engine restart loses keys
and says so; a CLI run with no supplied key fails with the explicit §3 error and
not a skip; a remote connection does not offer the field.

The migration test that matters most is the refusal path — the success path is
the one that will be exercised by hand on the first run, and the refusal path is
the one nobody will ever see until it happens to a user.
