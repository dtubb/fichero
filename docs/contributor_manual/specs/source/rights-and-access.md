# Source Model — Rights, consent and access — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — a "Who may see this" section: recording rights and consent on a source or any
> part of it; community protocols and labels; restricting, redacting and truly removing
> material; and what exports and training sets do with restricted material.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — raised by review, 2026-09-19. The maintainer has
> ruled that it belongs in this set and who may act; the rest is PROPOSED.** A slice of the source model: read
> `source-model.md` first. Behaviour ids below have **no tags yet**. Nothing here is built.
> What exists today (VERIFIED on disk, `fichero_server/security/authz.py`): a person has one of
> three roles in a project: **owner**, **editor** or **viewer**. Nothing restricts anything
> below the level of a whole project. The sharing and accounts specs have not been read in
> full for this slice, and must be before approval.

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
  material. (Whether every editor sees it, or only those a record names, is an open
  question.)
- **Restricted** means those not allowed do not see a segment's picture, readings, marks or
  statements. For them it is **hidden, and the fact that something is hidden is shown** ("one
  passage on this page is restricted"). It is never silently dropped.
- **A reference does not leak.** A citable reference to a restricted segment opens to
  "restricted" for someone not allowed, never to its content.
- **Exports, training sets and the synced folder leave restricted material out by default**
  and say how many segments they left out. Including it takes a deliberate, recorded act by
  the owner.
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

## Behaviors (ids proposed; untagged until approval)

- `source.rights.record` — a rights and consent record can be attached to a project, a source
  or any segment, with labels from an open list.
- `source.rights.tighten-only` — a record passes downward; a lower level may restrict further
  and never loosen.
- `source.rights.who-acts` — owners and editors set rights records, restrict and redact; only
  the owner can purge.
- `source.rights.restricted-is-said` — for a viewer (and an editor the record does not admit) a
  restricted segment's content is hidden, and the page says that something is hidden.
- `source.rights.citation-does-not-leak` — a reference to a restricted segment opens to
  "restricted" for someone not allowed.
- `source.rights.exports-leave-out` — exports, training sets and the synced folder leave
  restricted material out by default and report how much.
- `source.rights.model-use` — a segment's record says whether it may go to a cloud model, a
  local model, or none; the engine refuses a workflow that would break it, and says why.
- `source.rights.redact` — redaction covers a segment's content visibly, everywhere it would
  appear, without deleting it.
- `source.rights.purge` — a purge removes a segment's content, cannot be undone, and leaves a
  note that says who, when and why.
- `source.rights.purge-reaches-derivatives` — a purge also removes search entries, vectors,
  pictures, synced-folder files and quoted evidence; a claim that rested on it is kept with a
  stated absence.

## Test matrix

To be filled at approval.

## Open questions

Most were ruled on 2026-09-19: see "Rulings of 2026-09-19" and "Still open" in
`source-model.md`.
