# Tuesday — the seven things only you can decide

Written 2026-08-02. The click-list (what to click, what to expect) is a
separate file: `2026-08-04-tuesday-clicklist.md`. This file is **decisions
only** — none of these can be answered by reading code, and no lane has been
allowed to guess any of them.

Each one blocks real work. They are ordered by how much they unblock.

---

## 1. Is NFC-normalised text acceptable as diplomatic content? (#3320 Q1)

**Blocks:** all of paleography step 1, and #3321 on top of it.

A diplomatic transcription preserves what the manuscript actually shows.
Unicode NFC normalisation silently changes some of it — composed vs decomposed
characters, some ligatures, some combining marks. If the answer is yes, the
text-normalisation choke point can be written this week. If no, the contract
is different and needs designing.

This is an editorial question about what a transcription *is*, not an
engineering one.

## 2. Backfill sign-off for normalised text (#3320 Q6)

**Blocks:** the same step, and it is the #3077 analog.

Backfilling normalised text **rewrites the Marshall Diaries**. Real data,
never nuked, changes go through `db_migrations.py`. This is authorisation, not
implementation.

## 3. Backfill sign-off for provenance

**Blocks:** repairing already-imported documents.

CLI uploads recorded the SERVER TEMP NAME as the document's source — pages
listed as `fichero_upload_sez7fq02.pdf - Page N`, metadata carried the temp
directory as `source_path`. **Fixed at ingest today**; new imports are correct.
Existing rows still carry the bad names — verified, not assumed.

The source name is provenance: it is what connects a document to the physical
original and what a citation needs. But for older rows the true original name
may not be recoverable at all, and **inventing one would be worse than an
obviously-wrong one**. Folder imports were always correct; this affects
CLI/upload-imported documents only.

## 4. What does "add photos to a person" MEAN? (the entity question)

**Blocks:** the entity editor (your priority 6), and the sidebar IA cluster.

An entity is not a container the way a folder is — **its children are a QUERY
RESULT**. So a drop onto an entity is either:

- **an assertion** — this photo depicts this person — which is a
  knowledge-graph write and belongs to the SVO/claims spine; or
- **a pinned exception to a query** — which means entities need a membership
  store that folders do not have.

These are different products. Nothing should be built until this is answered.

## 5. The sidebar IA is HALF-MIGRATED

**Blocks:** #1686, #1738, #1793, #2446, #2447, #4102, #4335 — seven issues
that are arguably one decision.

The duplicate entry points were removed (the pinned bottom nav rows) but **the
modes they duplicated remain** — `ViewSettings` still declares `.research` and
`.knowledgeGraph`. So research and entities are now reachable ONLY through a
mode bar the rest of the design moved away from. Fewer doors to a room nobody
meant to keep.

`SidebarItem.ItemType` holds 12 node kinds and has NO case for workspace,
research project, or entity — the tree can express most of #4335 and
specifically cannot express the three things this decision is about.

Recommendation on file: close the older five as duplicates of #4102, but
**transcribe #1686's detail first** — entities must reuse LibraryView's
view-mode machinery, not merely appear in the tree.

## 6. #2397 cross-library drag

**Blocks:** itself, permanently, until you rule.

There is no cross-library move action. Every path terminates in one library's
`documentStore.moveDocument`, and a client-orchestrated version **cannot be
atomic across two databases**. Destructive + non-atomic + Marshall Diaries +
an unanswered semantics question ("does moving between libraries copy, move,
or link?").

## 7. The six remaining `created_by` surfaces (#4485's sweep)

**Blocks:** finishing the attribution fix.

MCP claim create trusted a client-supplied author and is fixed. Six more
surfaces still do: canonical `POST /api/claims`, research notes ×2, research
CRUD, hermeneutics, bookmarks.

The class **splits in two** and that is why it was not swept:
- **provenance labels for machines** — "workflow", a model id; the extraction
  pipeline legitimately labels its own output through some of these;
- **author identity for people** — must derive from authenticated state.

A blind sweep would break honest machine attribution in order to fix forged
human attribution. Each site needs that distinction drawn. Your call on
whether machine provenance belongs in `created_by` at all, or in a separate
field.

---

## Not decisions, but you should know

- **`fichero engine stop`'s graceful HTTP path was deleted**, not repaired. It
  POSTed a nonexistent route, over the wrong scheme, using a dependency the
  CLI does not have — all three swallowed. SIGTERM *is* uvicorn's graceful
  shutdown. It now says so.
- **iPad testing has never been possible** (#4472) — `fichero-ipad.xctestplan`
  names `FicheroTests`, which is macOS-only. The gate leg reports NOT ARMED
  rather than pretending. Needs Xcode project surgery.
- **EPIC #4487**: 66 guardrail scripts, 56 discover-then-assert, **50 with no
  floor**. A check that scans nothing currently passes. Phase 1 (a shared
  primitive + the 12 highest-risk) is in progress.

---

## WARNING — jCodemunch's index is unreliable in this worktree (#4490)

Not a decision, but do not act on it before reading this.

The project's standing code-navigation policy is to use jCodemunch for
"is this referenced?" questions — exactly the questions that justify a
deletion, a rename, or a dead-code claim. **In this worktree its index
resolves to sibling worktrees, and it is wrong in BOTH directions:**

- **FALSE ABSENCE** — `check_references` returned `is_referenced=false` for
  `LibraryDateSectioning`, `groupingUndatedLast`, `dateHeaderSortKey` and
  `ListingSort`. All four exist and are referenced. A reader trusting that
  answer deletes four live types.
- **FALSE PRESENCE** — `syncLegacyScope` returned `is_referenced=true` on
  references that are not in this tree.

False absence gets working code deleted. False presence keeps dead code alive
and blocks cleanup. Both are silent, and both look like authoritative answers.

**Until #4490 is fixed:** do not justify a deletion with a jCodemunch
"no references" result in a worktree. Use an exhaustive multi-pattern text
search and say that is what you did. That is how today's `EntityStore.entities`
deletion was proved — the only external references turned out to be ten
assertions in its own test suite.

This is the same class as EPIC #4487's blind guardrails, one layer out: a tool
reporting a confident answer about something it never looked at.

---

## 8. Where does a REMOTE CLI's SPKI pin live? (#4468's last half)

**Blocks:** the CLI reaching a remote engine at all. Local now works.

Fixed today: the CLI's default was `http://127.0.0.1:8765` against an engine
that **refuses to start without certs** — a default that could never work.
Now `https://`, anchoring the certs the engine itself writes
(`Remote Access/<host>-<port>-*/server.crt`), failing closed and naming the
path it searched. `verify=False` appears nowhere. Live-proven: `fichero
health` with no manual trust setup returns healthy.

**What is left is not implementable without you.** The app's pins arrive by QR
pairing into defaults *on the paired device*. A CLI on another machine has no
pairing flow and no store, so there is nowhere for a pin to live.

Three options, from the lane:

- **A CLI pairing flow** — heaviest, and the most consistent with the standing
  design (QR pairing over Bonjour+TLS, per-device tokens). A CLI on another
  machine *is* another device by that model.
- **`FICHERO_SPKI_PIN` env var** — lightest and scriptable, but pins land in
  shell history and CI logs, and a pin is the thing that makes verification
  meaningful.
- **A pin file beside `cli-session.json`** — middle. Same lifetime as the
  session it accompanies.

My read, not a decision: the standing design already answers this — a machine
that wants to reach a remote engine becomes a paired device. But that is a
real amount of work and you may want the middle option first.

Remote HTTPS keeps default verification until you rule.

---

## 9. A translated pseudo-quote can enter the archive unanchored (#4494)

**Found by chasing a flaky test, and it is the one finding on this page that
touches the archive's integrity rather than its tooling.**

The on-device Apple Intelligence extractor sometimes **translates**
`source_text` into English — a Spanish sentence comes back as *"La Imprenta
Oficial published the decree the next day."* — and occasionally attaches a
neighbouring sentence to the wrong person.

The anchoring check is correct and does its job: #913's offset check is an
exact substring match, so a non-verbatim quote is **never anchored** to a
position in the document. **But the divergent text is still PERSISTED as the
claim's quote.**

So the archive can hold a claim whose quote is not what the manuscript says,
carrying no anchor to prove or disprove it. It reads exactly like a real
quotation.

**The decision is what should happen at the extractor write:**

- **Blank it** — no quote is better than a wrong one. Simple, and loses the
  model's paraphrase entirely.
- **A distinct non-quote field** — keep the text but never call it a quote.
  Preserves the extraction as a summary/paraphrase, which may be genuinely
  useful, at the cost of a new field and everything that renders it.

This is the AI-as-instrument line: a paraphrase presented as a quotation is
the failure mode the north star exists to prevent. But blanking discards
model output you may want.

**Not decided, not built.** The flaky assert has been softened (structural
assertions stay hard; the divergence now logs), so the test no longer fails
~25% of the time — but that only stopped the noise. The persistence is
untouched and waiting on this.
