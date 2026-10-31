"""#6295: the cap's models, refusal and pricing live in their own modules, so the two files already over a thousand lines
(`api/routes/system/recipes.py`, and the Swift store's) are not made longer by this feature. Review finding 8."""

from __future__ import annotations

from pathlib import Path

from fichero_server.api.routes.system import recipes

BASE_LINES = 3724  # recipes.py at the commit before #6295 (98990d947): it must not end up longer


def test_recipes_py_is_no_longer_than_it_was_before_the_cap_work():
    source = Path(recipes.__file__).read_text(encoding="utf-8")
    assert len(source.splitlines()) <= BASE_LINES


def test_the_cap_route_is_in_its_own_module_under_the_same_prefix(client):
    from fichero_server.api.routes.system import recipe_cloud_cap

    assert Path(recipe_cloud_cap.__file__).parent == Path(recipes.__file__).parent
    paths = {r.path for r in recipe_cloud_cap.router.routes}
    assert paths == {"/recipes/project/cloud-cap"}
    assert client.put("/api/recipes/project/cloud-cap", json={"cap_usd": 12}).status_code == 200
