# Source Model — Rights, consent and access — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — a "Who may see this" section: recording rights and consent on a source or any
> part of it; community protocols and labels; restricting, redacting and truly removing
> material; and what exports and training sets do with restricted material.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — raised by review, 2026-09-19. The maintainer has
> ruled that it belongs in this set and who may act; the rest is PROPOSED.** A slice of the source model: read
> `source-model.md` first. Every behaviour below is tagged **[GAP]** with its issue. Nothing here is built.
> What exists today (VERIFIED on disk, `fichero_server/security/authz.py`): a person has one of
> three roles in a project: **owner**, **editor** or **viewer**; and **grant-and-deny overrides
> on a target and everything under it** already exist, enforced on every audited write
> (`actions/registry.py`) and in search. They stop at a document, not a word. The sharing and
> accounts specs have not been read in full for this slice, and must be before approval.
>
> **Routed fact, 2026-09-20 (#4917, read in review; in the worktree, not yet committed when this
> was written).** The permission layer's one ancestor walk now resolves an artifact, segment,
> pass, match, version, forwarding note or carry to its document, then walks the folders above
> it. So a grant or deny on a document or folder reaches everything the source model hangs on
> that document, and a lookup fault denies. The walk still does **not** go below a document:
> an override placed on a segment id matches that id alone, because the walk does not follow
> `Segment.parent_segment_id`. If the maintainer rules that rights become grants and denies on
> a segment, the build is one more step in that same walk (segment, parent segment, document),
> never a second check. This changes nothing about the block below.
>
> **BLOCKED on the maintainer.** This slice was ruled into the set on 2026-09-19. Review then
> showed that a rights record with its own enforcement would be a second permission system
> beside the one that exists. The reviewers recommend: **the existing permission layer
> enforces; a rights record says what is meant and why** (and is turned into grants and denies
> on a segment id, one check). That is the maintainer's to rule; it is in the morning file.
> **Nothing here is built until then.** A second blocking question sat under purge: every
> action's record lives in a tamper-evident chain, so a purge could not reach words stored
> there. **That one was ruled on 2026-09-20:** each record is split into a chained part (who,
> what, when, ids, version numbers, a keyed fingerprint) and a content part outside the chain
> that a purge can blank, so the chain still checks out and the words are gone (see "Rulings
> of 2026-09-20" in `source-model.md`). Purge still waits on the first question, and on that
> split being built, which belongs to the audited-action layer, not to this set.

## Intent

Fichero is meant to serve under-resourced and Indigenous languages. Material in those
languages often carries obligations: a community's protocols about who may see, hear or
share something; a speaker's consent, which can be withdrawn; a family's privacy; a
repository's conditions. The field's name for the principle is CARE (collective benefit,
authority to control, responsibility, ethics), alongside FAIR; its working tools include
Traditional Knowledge and Biocultural labels.

Because the source model lets anything be addressed down to a word, a restriction must be
able to apply down to a word too: one name in a diary; one passage of a recording; one
photograph on a page. And because the model exports everything and builds training sets,
restrictions have to hold **before** any of that exists, not be added after.

(Evidence note: CARE and the TK labels are named from general knowledge and are to be checked
against their sources before approval.)

## The design (proposed)

- **A rights record** can be attached to a project, a source, or any segment. It says: who
  holds rights or authority; what was consented to, by whom, when; any conditions; any
  **labels** from an open list; who recorded this, and when. Traditional Knowledge and
  Biocultural labels belong to the communities that apply them and are administered by Local
  Contexts; Fichero carries them faithfully and does not invent them. A project can also keep
  labels of its own.
- **It passes downward, and only tightens.** A rights record on a project covers everything in
  it; a record lower down may restrict further, never loosen what is above it.
- **Who may do what** (ruled 2026-09-19). **Owners and editors** can set rights records,
  restrict and redact. **Only the owner can purge.** A **viewer** never sees restricted
  material. **Ruled 2026-09-20: only the people a rights record names see restricted
  material**; being an editor is not enough.
- **Restricted** means those not allowed do not see a segment's picture, readings, marks or
  statements. For them it is **hidden, and the fact that something is hidden is shown** ("one
  passage on this page is restricted"). It is never silently dropped.
- **A reference does not leak.** A citable reference to a restricted segment opens to
  "restricted" for someone not allowed, never to its content.
- **Exports, training sets and the synced folder leave restricted material out by default**
  and say how many segments they left out. Including it takes a deliberate, recorded act by
  someone allowed to restrict (an owner or an editor). The filter sits **once**, in the
  exporter's one record stream, not in each writer (routed to `export/exporter.md`).
- **Sent to a model?** Whether a segment may be sent to a cloud model, to a local model only,
  or to none, is part of its rights record. The engine refuses, and says why, when a workflow
  would break it.
- **Redaction** is a verb of its own, different from delete: the segment stays, its content is
  covered for everyone not allowed, and the covering is visible as a covering (in the Source
  view, the Reader, exports and pictures of the page).
- **Removal on request.** "Nothing is ever destroyed" cannot be the whole story when consent
  is withdrawn. A **purge** truly removes a segment's content. Its reach is stated: the
  readings, pictures, marks and rights-holder's words; everything worked out from them
  (search entries, vectors, word-level analysis); the files in the synced folder; and the
  quoted words inside any claim that rested on it. A claim itself is kept, with a plain note
  that its evidence was removed, so nothing points at nothing. A purge cannot reach what has
  already left the machine (an export, a shared training set), and Fichero keeps no list of
  what was exported (ruled 2026-09-19): following that up is the researcher's own job, and
  the purge says so plainly. A purge is rarer and louder than delete; it cannot be
  undone; and it leaves a note that something was purged, by whom, when and why, without
  saying what it was.
- All of these are audited actions, and work the same from the app, MCP and the command
  line.

## Behaviors (every one is **[GAP]**: designed, not built; each cites its issue on milestone `source-model`, 322)

- `source.rights.one-check` — **[GAP]** (#4953) a rights record is enforced by the existing permission layer (a
  grant or deny on a segment id, inherited the way it already is); there is no second check.
  (Recommended; blocked on the maintainer with the rest of this slice.)
- `source.rights.record` — **[GAP]** (#4953) a rights and consent record can be attached to a project, a source
  or any segment, with labels from an open list.
- `source.rights.tighten-only` — **[GAP]** (#4953) a record passes downward; a lower level may restrict further
  and never loosen.
- `source.rights.who-acts` — **[GAP]** (#4953) owners and editors set rights records, restrict and redact; only
  the owner can purge.
- `source.rights.restricted-is-said` — **[GAP]** (#4953) for anyone not allowed to see it (always a viewer, and any editor or owner the
  rights record does not name: ruled 2026-09-20), a restricted segment's content is hidden, and the page says
  that something is hidden.
- `source.rights.citation-does-not-leak` — **[GAP]** (#4953) a reference to a restricted segment opens to
  "restricted" for someone not allowed.
- `source.rights.exports-leave-out` — **[GAP]** (#4953) exports, training sets and the synced folder leave
  restricted material out by default and report how much.
- `source.rights.model-use` — **[GAP]** (#4953) a segment's record says whether it may go to a cloud model, a
  local model, or none; the engine refuses a workflow that would break it, and says why.
- `source.rights.redact` — **[GAP]** (#4953) redaction covers a segment's content visibly, everywhere it would
  appear, without deleting it.
- `source.rights.purge-is-an-action` — **[GAP]** (#4953) a purge is an action in the one audited registry, the same
  shape as the purge that exists for draft entities; not a separate route.
- `source.rights.purge` — **[GAP]** (#4953) a purge removes a segment's content, cannot be undone, and leaves a
  note that says who, when and why.
- `source.rights.purge-reaches-derivatives` — **[GAP]** (#4953) a purge also removes search entries, vectors,
  pictures, synced-folder files and quoted evidence; a claim that rested on it is kept with a
  stated absence.

## Test matrix

To be filled at approval.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
