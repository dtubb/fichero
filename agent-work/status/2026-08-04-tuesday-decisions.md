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
