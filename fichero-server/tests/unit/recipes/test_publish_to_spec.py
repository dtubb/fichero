"""`source.job.publish` (docs/contributor_manual/specs/source/models-chains-and-projects.md), tested to the spec.

Through the project routes and the real scheduler, with the recipe execution tests' stub cards (Kraken at
its runtime); the site is the one site export's.
"""
from __future__ import annotations


from tests.unit.recipes.test_recipe_execution_to_spec import (  # noqa: F401  (fixtures)
    _finished,
    _recipe,
    _save,
    _start,
    engine,
    pages,
)

LINES = {"id": "lines", "job": "find-lines", "model": {"kraken": "blla", "kraken_version": "bundled"}}
READ = {"id": "read", "job": "read-a-line", "model": {"zenodo": "10.5281/zenodo.13788177"}}


def test_source_job_publish(client, db, pages, tmp_path, engine):  # noqa: F811
    """source.job.publish: "a recipe's `publish` step writes the project as a static website (an 11ty project
    that builds with `npx @11ty/eleventy` and deploys to Netlify) through the one site export
    (`export_service.export_eleventy_site`), into the folder its `where` setting names on the engine's disk, as
    a card of a started recipe; publishing again rewrites that site in place. A step that names no folder is
    skipped and says so.\""""
    site = tmp_path / "site"
    export = {"id": "export", "job": "export", "settings": {"formats": ["pagexml"], "folder": str(tmp_path / "ed")}}
    _save(client, _recipe(tmp_path, LINES, READ, export, {"id": "site", "job": "publish", "settings": {"where": str(site)}}))
    run = _finished(client, _start(client))
    assert run["state"] == "done", run
    assert [(s["steps"], s["card"], s["state"]) for s in run["steps"]][-1] == (["site"], "publish", "done")
    assert (site / "eleventy.config.js").is_file() or (site / ".eleventy.js").is_file()
    assert (site / "netlify.toml").is_file() and (site / "src" / "index.md").is_file()
    pages_written = sorted(p.name for p in (site / "src").glob("*.md") if p.name.startswith("p"))
    assert pages_written == ["p0.png.md", "p1.png.md"]  # named as the site export names a page
    assert "Yten dixo el testigo" in (site / "src" / "p0.png.md").read_text(encoding="utf-8")

    again = _finished(client, _start(client))
    assert again["state"] == "done" and (site / "src" / "p0.png.md").is_file(), "publishing again rewrites in place"

    _save(client, _recipe(tmp_path, LINES, READ, export, {"id": "site", "job": "publish"}))
    plan = client.get("/api/recipes/project/start").json()
    assert any(s["step"] == "site" and "no folder" in s["why"] for s in plan["skipped"])
