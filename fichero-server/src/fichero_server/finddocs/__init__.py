"""Find the Documents: where documents start and end in a box of loose pages (`finddocs.*`, #5550).

`docs/contributor_manual/specs/source/finding-documents.md`. `cues` is the table of opening, closing and
kind cues (languages add rows); `propose` turns a folder's pages into a proposal (leaves, findings,
boundaries, kinds, groups) and scores one against a person's breakdown; `job` runs it as one background
job and stores the proposal as a hypothesis (a `grouping` artifact on the folder, never a change);
`accept` is the one audited action that makes the accepted documents group nodes, undone as one.
"""

#: The recipe step's default (`finddocs.recipe-step`): propose, and accept by itself only a document this sure.
#: Taken 2026-10-07 for the maintainer's confirmation (needs-your-decision): onboarding should organise by
#: itself, so the clear cases are accepted and the rest wait as proposals. One undo restores either way.
AUTO_ACCEPT_ABOVE = 0.95
