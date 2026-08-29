# Chapter 6. Workflows


### About Workflows

Workflows are Fichero’s step-by-step processing pipelines: transcribe a scan, extract people and places, produce a catalogue-style artifact. Every workflow run is recorded, and everything a workflow produces carries provenance — which document, which page, which workflow, which model.

### Presets

Fichero ships with roughly fifty ready-made workflow presets, including transcription workflows, a six-stage catalogue chain, and a family of paleography workflows for difficult historical scripts. Presets are the fastest way to start: pick documents, pick a preset, run it.

### Running a Workflow on a Selection

Workflows can be run from several places:

- 
- 
- 

toolbar run actionsthe workflow’s own viewthe right-click context menu on selected items in the libraryThe library browser passes your entire multi-selection into the run, which matters for catalogue-style workflows that need the whole selected set rather than one file at a time. To run a workflow: select documents in Library mode, then choose the workflow from the run menu or the context menu.

### Building Workflows in the Visual Editor

Workflows mode is where you build your own pipelines. You build a workflow visually by placing nodes on a canvas and connecting them. The left pane lists your saved workflows, grouped into folders; the canvas is where you arrange and connect the steps. Selecting a node lets you adjust its settings, such as which AI model that step uses. The model picker shows the models you have configured in Settings.

### Watching Activity

Activity is Fichero’s running and historical workflow surface. While workflows execute, Fichero keeps their state visible through the Activity mode, sidebar indicators, and progress updates. This is where you answer: Is my import still processing? Did the catalogue run finish? Which workflow run produced this output?

### Artifacts

Workflow outputs land as artifacts attached to the documents they came from, visible in the inspector’s **Artifacts** section. Each artifact records its provenance. You can review artifacts, correct them, or delete them; the AI’s output never silently replaces your sources.

### Datasets

Catalogue-style workflows produce structured, tabular results — inventories, indexes, tables of extracted fields — attached to your documents as artifacts. These datasets can be reviewed in the app like any artifact, and the underlying records can be exported for use outside Fichero. As with all workflow output, every row carries provenance back to the page it came from.
