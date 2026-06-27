# Curation, Notes, Annotations, and Workflows

## Table of Contents

- [Entity and Claim Curation](#entity-and-claim-curation)
- [Merge, Undo, and Prune Behavior](#merge-undo-and-prune-behavior)
- [Annotations and Notes in Daily Work](#annotations-and-notes-in-daily-work)
- [Running Workflows](#running-workflows)
- [Watching Activity](#watching-activity)

## Entity and Claim Curation

Fichero's inspector supports real curation actions for both entities and claims.

For multi-selected entities, the current UI exposes:

- `Approve`
- `Reject`
- `Suppress`
- `Merge`

For multi-selected claims, the current UI exposes:

- `Approve`
- `Reject`
- `Suppress`
- `Merge`
- `Prune trivial`

Most of these actions can be applied at two scopes:

- the current page or folder
- library-wide

Library-wide suppression can also write persistent suppress rules, so the curation decision can continue to affect future imports and later refreshes.

## Merge, Undo, and Prune Behavior

When you merge entities or claims, Fichero keeps one surviving canonical item and folds the others into it.

The current app also includes curation history for entity merge and split operations, with undo actions exposed from the audit history section in the knowledge-graph inspector.

Claim pruning is aimed at trivially true claims. In the current UI, pruning:

- can target the current document scope or the whole library
- refreshes the inspector after the update
- may write a persistent suppress rule in library-wide cases

Claim unmerge is not yet exposed as a finished UI path, so do not expect a polished reverse-merge workflow for claims in current builds.

## Annotations and Notes in Daily Work

The practical distinction is:

- use annotations when the note belongs to a page, text span, or highlighted region
- use notes when the note belongs to the document as a whole

That distinction matters because annotations can be revealed back on the page and promoted into claims, while notes are maintained as linked document notes.

## Running Workflows

Workflows can be run from multiple surfaces:

- toolbar run actions
- workflow-specific views
- selection-driven library actions
- context menus for selected items

The library browser can pass the entire current multi-selection into a workflow run. That matters for catalogue-style workflows that need the whole selected set, not one file at a time.

## Watching Activity

Activity is Fichero's running and historical workflow surface.

While workflows are executing, Fichero keeps execution state visible through:

- activity views
- sidebar indicators
- workflow progress and status updates

In practice, this is where you go to answer:

- Is my import still processing?
- Did the catalogue run finish?
- Which workflow thread produced this output?
