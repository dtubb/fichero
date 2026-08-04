# Tuesday handover — 2026-08-04

`main` is at `ed2fb57ce`, build-verified on Mac **and iPad**. Read section 1
before you start; the rest you can read after the release is running.

---

## 1. What only you can decide

Eight things block work. Nothing else does.

### Multi-select grammar — three surfaces, one underlying question

**Q1. Inspector lists: full Mac selection grammar, or is native `List` enough?**
Native `List(selection:)` gives arrows and ⇧-click but not ⌘A, ⇧-arrow range, or
the anchor rules that make multi-select feel right rather than nearly right.
Wiring `SelectionGrammar` in means deciding **what ⇧ extends *along*** in a list
grouped into sections by entity kind — across sections, or within one? Not
guessed.

**Q4. Sidebar: adopt `SelectionGrammar`?** AppKit already supplies ⇧-range and
⌘-toggle, so nothing is visibly broken. Same underlying question: in a *tree*,
does ⇧ extend along visual DFS order across libraries, or within one library?

> Q1 and Q4 are the same decision twice. Answer "what does ⇧ extend along" once
> and both follow.

**Q2. iPad: should inspector rows get `.swipeActions`, or stay context-menu-only?**
There is not one `.swipeActions` or `EditButton` in the whole inspector. On iPad,
delete is reachable for artifacts and entities only by long-press, and for
annotations **not at all**. Swipe is the native idiom, but it changes the Mac
surface too unless `#if os(iOS)`-gated — and this codebase's rule is
feature-first, not OS-first.

**Q3. Should the inspector differ from the library on multi-select, and where?**
`DocumentInspectorRelatedTab` documents its single-selection as deliberate
("multi-select would be an affordance for nothing") and that reads right.
Annotations and citations are also single-selection with **no reasoning
recorded**, and a user who just learned ⌘-click in the library will try it there.
Deliberate, or drift?

**Q5. Should eight inert sidebar row kinds be selectable at all?** Clicking a
chain, a schedule, a structure node or a library header paints a selection and
changes nothing. Either make them non-selectable, or give them a detail view.

**Q6. Should the sidebar have empty states?** It has none, deliberately ("empty
arrays render nothing"). Defensible for a tree — but "no results" after a filter
is different: the user typed something and got silence.

### Paleography: stop the ensemble at t2, or switch to Vision? (#3905)

The one authorised paid run is done. Accent-blind CER, lower is better:

| | |
|---|---|
| Free Apple Vision, whole page | **0.3571** |
| Free Apple Vision, the same tiles the ensemble sees | 0.4586 |
| Paid ensemble **t2** | **0.3971** ← its best |
| Paid ensemble **t4** — the pass whose text becomes the page | **0.8814** |

You pre-decided "if it loses to free Vision, make Vision the default tier". It
does lose — **but not for the reason that sentence assumed.** The paid model is
competitive at t2 and then *destroys its own work*: t3 and t4 make it 2.2×
worse. t4's diplomatic CER of 1.03 means more edits than there are characters.

So there are two different products, and it is your call:
- **Switch the default to Vision.** Gives up t2, the best result measured.
- **Stop the ensemble at t2.** Beats free OCR of the same tiles, at 8 calls
  rather than 12.

Apple Vision is *already* the factory default (`FACTORY_AI_DEFAULTS`, on-device
since #4325), so "switch to Vision" needs no code — your machine's app DB
overrides it. Nothing was changed.

Full numbers: `agent-work/status/2026-08-03-paleography-ensemble-measurement.md`.

### Preset validation: approve the remaining spend? (#4501 phase 3)

39 presets, 13 validated and free under any configuration. The rest:

| configuration | free | billable |
|---|---|---|
| factory defaults (a new install) | **37 of 39** | 1 |
| **your machine's app DB** | **13 of 39** | 25 |

Validating every billable preset once, on one page, is **~$0.19** (61 calls at
$0.00315). The money is not the question — the question is whether you want
them validated at all, and on which configuration. Recommend factory defaults:
zero cost, and it is what a new user actually gets.

`agent-work/status/2026-08-03-preset-cost-estimate.md`.

---

## 2. What is true about the build

- `main` is **build-verified on Mac and iPad**. iPad tests ran for the first
  time today — 9 passing.
- **The release path is fixed.** The app is stapled *before* the DMG seals it
  (#4491), and `notarytool --wait` is replaced by submit-and-poll.
- **The release is 5–10 minutes longer and will look stalled while polling.**
  That is normal. **Do not kill it.**

---

## 3. What was found that changes what you believe

**A preset cannot be known free from its JSON.** Not one of the 39 pins a
provider; every model-using node inherits your app database. "Is this free?" is
a property of *preset + database*, and the answer differs between your machine
and a fresh install. This cost money twice today — once from a probe expected to
be on-device, once from a triage that classified presets by reading their files.
`fichero workflow preview-cost NAME` now answers it before you run, with a
FREE/COSTS MONEY verdict and a SURPRISES block for nodes that bill while looking
free.

**The paid ensemble degrades its own output.** Not "the paid model is worse" —
it is competitive at t2 and then the last two passes destroy it. Any plan
assuming more passes means better transcription needs re-checking.

**MCP ran every workflow on zero documents while reporting success.** Both MCP
surfaces sent `inputs={"files": [...]}`; nothing reads `files` — the Files node,
the CLI and SwiftUI all read `selected_doc_ids`. Found by routine verification,
which means nothing was watching one of your three instruments. Fixed, and the
new test asserts against the *engine's* request model rather than the sender's
own output.

**The sidebar was the one document surface not using `DocumentTitle`.** That is
why the storage-filename leak needed three sweeps to clear: each sweep fixed the
surfaces that shared the composer and left the one that did not.

---

## 4. Still broken or unverified

**iPhone-to-Mac pairing (#4465).** The *protocol* is verified — automated tests
drive login → pair-code → device token, with reuse and expiry rejected. What is
unverified is the iOS client's use of it, Bonjour discovery, the transport, and
the physical round trip. **Only the last needs a phone.**

⚠️ **A phone cannot reach the Mac over plain wifi — by design.** The engine binds
loopback and refuses non-loopback binds; the supported path is `tailscale serve`
or SSH forwarding. To try it you need: tailscale on both devices on the same
tailnet, `tailscale serve` pointed at the engine's loopback port, then generate a
pairing code on the Mac and enter it on the phone. *Same wifi alone will not
work.* Steps 1–6 in
`agent-work/status/2026-08-03-pairing-verification-requirements.md`.

**Silent-failure ledger: net +3 today** (246 → 249 only-log broad handlers).
Five were added by today's work, two were removed by it. That is the honest
summary of a day spent on exactly this: the codebase got slightly *noisier*
about its own failures in count, while the ones that mattered — a vision fanout
transcribing nothing, catalogue deleting corrections, MCP running on zero
documents — were removed. Of the five new ones, three are legitimate (a
migration matching its neighbours' convention, terminal-path bookkeeping that
must never fail a run, and a resolver that genuinely falls back to shipped
presets) and two are covered by a different validator. None needed fixing.

**The four Box libraries** — you are checking those yourself.

**The second full engine suite** was still running when this was written. The
first found 10 failures; 5 were a regression that is now fixed, and the rest were
pre-existing vision-fixture staleness now also fixed.

---

## 5. Where the process failed today

A handover that reads as an unbroken success is not useful to someone about to
ship. Three of these are the manager's, one is mine, and all four are the same
shape — *something was verified in a way that could not have detected the
problem*.

- **#4415 was reported fixed when its guard was wired to a caller Catalogue
  never invokes.** The tests were real and green; they tested the wrong caller.
  Catalogue was still hard-deleting corrected artifacts.
- **#4497 shipped a regression that made the vision fanout do nothing** — caught
  only by the full suite, hours later, because it was verified with targeted
  tests that did not touch the vision suite.
- **A lane was told to reset when its unmerged paid-run results were the only
  copy.** The STOP rule caught it. That rule prevented data loss three times
  today, twice from instructions the manager sent.
- **I chained a `reset --hard` into the same command as the check that was
  supposed to gate it**, which defeated the rule entirely. It cost nothing only
  because the commit had already been merged elsewhere.

The pattern worth keeping: **the full suite found what targeted verification
could not**, four separate times. Targeted tests are how today moved fast; they
are also how three of these four shipped.

---

# LATE MONDAY — what landed after the handover was written

`integration` is at `2f4ea67da`, pushed, app + test targets green, **81
guardrails** (one new), backend 2,435 passed.

## Closed with evidence (7)

#4486, #4488, #4489, #4500, #4505, #4508, #4509.

**#4509 is the one to know about.** Wiring purge through the audited action
layer (#4488) exposed that `_ensure_transaction_started` issues `BEGIN` raw,
outside the reopen-and-retry every other DuckDB entry point has. So after a
poisoned connection — disk full, OOM mid-write, I/O error at checkpoint — **every
audited write on that library fails until the engine restarts**, while reads keep
working because reads go through the door that recovers. This box hit 96% disk
last night, which is the triggering condition.

It stayed invisible because of a test-coverage asymmetry: four audited writes,
zero closed-connection tests between them, and the only such test covered
purge — the one write NOT on the audited path. `COMMIT`/`ROLLBACK` were
deliberately left without recovery: a reopened COMMIT returns green having
committed nothing.

## Deliberately NOT closed (4)

#2386, #4458, #4459, #4386 — fixed and pushed, but drag-drop and hit-target
geometry that a unit test cannot prove. #3390, #702 and #570 were each closed on
a real commit while drag-drop stayed broken. They are on the click-list.

## The pattern worth acting on

**Seven issues where the code contradicts the issue text.** #4408 fixed the day
it was filed and shipped; #4388 fixed 1 August; #4386's supposed cause predated
the report by twelve days; #4311's export half already implemented; #4486's
premise wrong in both halves; #3686 not an oversight at all. The backlog
systematically overstates what is broken, because issues are written once and
the code moves underneath them.

That is why the sweeps are worth more than they look: they correct the map the
work is planned from. **11 issues have a shipped fix and are still open** — three
since 13 July.

## Two refusals that were right

1. **#3686.** I told a lane to wire the four missing pane focus bindings. It
   found `7c27e9fe2` (2026-04-16): those bindings existed and were removed
   **because the app crashed on launch**. My instruction would have restored the
   crash. It also said "do not dispatch this to another lane either", which is
   what actually closed the hole. Warning is now on the issue.
2. **#4486.** I told a lane to add a `prune` action to make a documented rule
   true. It found `testPruneTrivialIsKnowinglyStillDirect` — a test whose
   purpose is recording that someone already decided against exactly that — and
   surfaced the argument I had not heard: the store's scope is one document or
   entity, prune is library-wide, so the action could not refresh what it had
   just changed. Ruling: recorded decision stands, fix the prose instead.

## One thing I could not close

`ClaimChangeDeliveryTests` **compiles but I have no passing result.** Running
`FicheroTests` fails on `Could not connect to the server` at
`https://127.0.0.1:8765/api/documents/roots` — the test HOST dials a live engine
at launch, so Swift unit tests need an engine they should not need. Worth fixing
on its own account.

Stated this way on purpose: built-green is not passes, and substituting one for
the other is what this whole day was about.
