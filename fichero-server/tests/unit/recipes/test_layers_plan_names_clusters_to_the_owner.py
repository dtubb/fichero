"""Review 133: the Start plan answered by `POST /api/recipes/project/layers` names the clusters set up here to the
owner, as `GET /api/recipes/project/start` does, and to nobody else (review 124: every /api/hpc route is owner-only)."""
from __future__ import annotations

import pytest

from tests.unit.api.test_add_a_layer_later import (  # noqa: F401  (fixtures)
    _kraken_readers_on_this_mac,
    hold_the_run,
    project,
)


@pytest.mark.parametrize("owner", [True, False])
def test_adding_a_layer_answers_a_plan_with_the_owners_clusters(client, project, monkeypatch, owner):  # noqa: F811
    from fichero_server.api.routes.system import recipes as routes

    monkeypatch.setattr(routes, "_cluster_names", lambda request: ["Rorqual"] if owner else [])
    seen, real = [], routes._start_plan

    def plan(db, folder_id=None, *, clusters=()):
        seen.append(list(clusters))
        return real(db, folder_id, clusters=clusters)

    monkeypatch.setattr(routes, "_start_plan", plan)
    r = client.post("/api/recipes/project/layers", json={"layers": ["publish"]})
    assert r.status_code == 200, r.text
    assert seen and seen[-1] == (["Rorqual"] if owner else [])
