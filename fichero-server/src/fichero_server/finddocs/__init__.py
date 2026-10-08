"""Find the Documents: where documents start and end in a box of loose pages (`finddocs.*`, #5550).

`docs/contributor_manual/specs/source/finding-documents.md`. `cues` is the table of opening, closing and
kind cues (languages add rows); `propose` turns a folder's pages into a proposal (leaves, findings,
boundaries, kinds, groups) and scores one against a person's breakdown; `job` runs it as one background
job and stores the proposal as a hypothesis (a `grouping` artifact on the folder, never a change);
`accept` is the one audited action that makes the accepted documents group nodes, undone as one.
"""

#: The one default (`finddocs.recipe-step`, ruled by the maintainer 2026-10-08, #5550): Find the Documents
#: accepts by itself a document at least this sure, and proposes the rest for a person. It is the recipe
#: step's setting and the run's (`FindDocumentsRequest.accept_above`, so the route, MCP and CLI) when left
#: out; null leaves every proposal for a person. One undo restores what it accepted.
AUTO_ACCEPT_ABOVE = 0.95
