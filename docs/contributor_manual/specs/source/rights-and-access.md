# Source Model — Rights, consent and access — Design Spec (#TBD)

> Milestone: source-model
> Manual: TBD — a "Who may see this" section: recording rights and consent on a source or any
> part of it; community protocols and labels; restricting, redacting and truly removing
> material; and what exports and training sets do with restricted material.
>
> Design-led (Testing Constitution). The creative director owns this intent; tests enforce it;
> code makes them pass. **Status: DRAFT — raised by review, 2026-09-19. Not yet discussed with
> the maintainer; every part of it is PROPOSED.** A slice of the source model: read
> `source-model.md` first. Behaviour ids below have **no tags yet**. Nothing here is built.
> What accounts, sharing and roles exist today has NOT been read for this slice; it must be
> before approval (see `multi-user` and sharing specs).

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
  **labels** from an open list (Traditional Knowledge and Biocultural labels among them; a
  project can add its own community's); who recorded this, and when. It is inherited
  downward like language is, and can be tightened at any level.
- **Restricted** means some people may not see a segment's picture, readings, marks or
  statements. For them the segment is **absent, and said to be absent** ("one passage on this
  page is restricted"). It is never silently dropped, and its existence is not hidden from
  the record.
- **Exports and training sets leave restricted material out by default** and say how many
  segments they left out, in the loss report. Including it takes a deliberate, recorded act
  by someone allowed to.
- **Sent to a model?** Whether a segment may be sent to a cloud model, to a local model only,
  or to none, is part of its rights record. The engine refuses, and says why, when a workflow
  would break it.
- **Redaction** is a verb of its own, different from delete: the segment stays, its content is
  covered for everyone without the right, and the covering is visible as a covering (in the
  Source view, the Reader, exports and pictures of the page).
- **Removal on request.** "Nothing is ever destroyed" cannot be the whole story when consent
  is withdrawn. A **purge** truly removes a segment's content (its readings, pictures, marks
  and statements, and copies in search and vectors). It is rarer and louder than delete; it
  cannot be undone; and it leaves a note that something was purged, by whom, when and why,
  without saying what it was.
- All of these are audited actions, and work the same from the app, MCP and the command
  line.

## Behaviors (ids proposed; untagged until approval)

- `source.rights.record` — a rights and consent record can be attached to a project, a source
  or any segment, with labels from an open list, and is inherited downward.
- `source.rights.restricted-is-said` — a restricted segment is absent for those without the
  right, and the absence is stated.
- `source.rights.exports-leave-out` — exports and training sets leave restricted material out
  by default and report how much.
- `source.rights.model-use` — a segment's record says whether it may go to a cloud model, a
  local model, or none; the engine refuses a workflow that would break it, and says why.
- `source.rights.redact` — redaction covers a segment's content visibly, everywhere it would
  appear, without deleting it.
- `source.rights.purge` — a purge truly removes a segment's content and what was worked out
  from it, cannot be undone, and leaves a note that says who, when and why.

## Test matrix

To be filled at approval.

## Open questions

1. Is this the right place for rights and access, or does it belong with accounts and sharing?
2. Who in a project may restrict, redact and purge?
3. Which label sets ship with Fichero?
4. Does a purge also reach backups and exports already made (it cannot reach what has left
   the machine; should Fichero keep a list of what was exported, so the owner can follow up)?
