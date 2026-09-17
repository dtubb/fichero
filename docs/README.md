# Fichero Documentation

Start with **[What is Fichero?](user_manual/guide/Part%20I.%20Getting%20Started/1-introduction/1-philosophy-of-fichero.md)**, then the **[User Guide](user_manual/README.md)** for installing Fichero and working with sources.

This folder is both the source for the Fichero website (built with MkDocs) and the documentation for [Fichero](../README.md) itself. `docs/` is the folder MkDocs builds the site from (`docs_dir: docs` in [`../mkdocs.yml`](../mkdocs.yml)). The docs are browsable as source on GitHub, or on the site: https://tubb.ca/apps/fichero.

This `README.md` is the GitHub folder landing page. [`index.md`](index.md) is the published homepage. `mkdocs.yml` excludes this `README.md` from the site.

This folder contains three manuals, plus the release-notes plumbing for the homepage:

- **[`user_manual/`](user_manual/README.md)**: the User Guide. Authored by Daniel Tubb in Tinderbox and exported here, organized as folders = Parts (`guide/Part I. Getting Started/`, `guide/Part II. Projects/`, …).
- **[`reference_manual/`](reference_manual/features.md)**: the Reference Manual: the app's UI elements, keyboard shortcuts, glossary, and the full workflow/tool reference. Generated programmatically from the app's source code.
- **[`contributor_manual/`](contributor_manual/README.md)**: the Contributor Guide: architecture, setup, testing, and release process. Written mostly by AI coding agents, largely unreviewed by a human.
- **[`contributors.md`](contributors.md)**:  the people who have contributed to making or testing Fichero.
- **`_latest.md`** / **`_releases.md`**: generated release-note snippets (by `scripts/gen_site_releases.py`) pulled into `index.md`.
