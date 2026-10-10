"""Find the Documents: where documents start and end in a box of loose pages (`finddocs.*`, #5550).

`docs/contributor_manual/specs/source/finding-documents.md`. `cues` is the table of opening, closing and
kind cues (languages add rows); `propose` turns a folder's pages into a proposal (leaves, findings,
boundaries, kinds, groups) and scores one against a person's breakdown; `job` runs it as one background
job and stores the proposal as a hypothesis (a `grouping` artifact on the folder, never a change);
`accept` is the one audited action that makes the accepted documents group nodes, undone as one.
"""

#: The one default (`finddocs.recipe-step`, #5550): the confidence at or above which Find the Documents
#: accepts a document's boundaries by itself; None proposes everything for a person. Ruled 2026-10-10: off
#: (None) until a box a person broke down is scored and shows boundaries at least 99% right; then it is set
#: to the measured level. It is the recipe step's setting and the run's (`FindDocumentsRequest.accept_above`,
#: so the route, MCP and CLI) when left out. One undo restores what a run accepted.
AUTO_ACCEPT_ABOVE: float | None = None
