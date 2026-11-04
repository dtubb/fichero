"""`ai.cloud.monthly-cap-in-settings` (#6346): the app's monthly cap is the default of a project with no cap answer of its own;
a project's own answer wins; with neither it is US$10 as before."""
from __future__ import annotations

import pytest

from fichero_server.llm import spend


@pytest.fixture
def app_caps(monkeypatch):
    held: dict = {}
    monkeypatch.setattr(spend, "app_cap_usd", lambda key: held.get(key))
    return held


def _project(tmp_path, answers: str = "") -> str:
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\n" + answers)
    return str(tmp_path / "P.fichero")


def test_with_no_answer_and_no_app_setting_the_cap_is_ten(tmp_path, app_caps):
    assert spend.cap_usd(_project(tmp_path)) == 10.0


def test_the_app_cap_fills_in_for_a_project_with_no_answer(tmp_path, app_caps):
    app_caps[spend.APP_MONTHLY_KEY] = 25.0
    assert spend.cap_usd(_project(tmp_path)) == 25.0


def test_the_projects_own_answer_beats_the_app_cap_either_way(tmp_path, app_caps):
    app_caps[spend.APP_MONTHLY_KEY] = 25.0
    assert spend.cap_usd(_project(tmp_path, "cloud_spend_cap_usd: 3\n")) == 3.0
    assert spend.cap_usd(_project(tmp_path / "b", "cloud_spend_cap_usd: 100\n")) == 100.0


def test_an_app_cap_of_zero_is_a_cap(tmp_path, app_caps):
    app_caps[spend.APP_MONTHLY_KEY] = 0.0
    assert spend.cap_usd(_project(tmp_path)) == 0.0
