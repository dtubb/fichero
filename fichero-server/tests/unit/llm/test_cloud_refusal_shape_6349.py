"""`ai.cloud.one-typed-refusal` (#6349, #6350): every refusal for money or images is one served shape with its fixes."""
from __future__ import annotations

import pytest

from fichero_server.llm import EgressRefusedError, refusal, spend


@pytest.fixture(autouse=True)
def _no_app_caps(monkeypatch):
    held: dict = {}
    monkeypatch.setattr(spend, "app_cap_usd", lambda key: held.get(key))
    spend._RESERVED.clear()
    return held


def _project(tmp_path, answers: str = "") -> str:
    folder = tmp_path / "P.fichero" / "recipe"
    folder.mkdir(parents=True)
    (folder / "setup.yaml").write_text("cloud_allowed: true\n" + answers)
    return str(tmp_path / "P.fichero")


def _kinds(r):
    return [f.kind for f in r.fixes]


def _over(library, worst):
    with spend._LOCK:
        over = spend._over_cap(library, 0.0, worst)
    return spend.cap_refusal(library, worst, over)


def test_a_monthly_cap_names_the_figures_and_offers_raise_once_and_settings(tmp_path):
    lib = _project(tmp_path, "cloud_spend_cap_usd: 1\n")
    spend._book(lib, 0.9)
    r = _over(lib, 0.2)
    assert (r.kind, r.scope, r.project) == ("cap-monthly", "project", "P")
    assert r.cap_usd == 1.0 and r.spent_usd == pytest.approx(0.9) and r.estimate_usd == 0.2
    assert "$1.00 a month" in r.words
    assert _kinds(r) == ["raise-to", "over-cap-once", "open-settings"]
    assert r.fixes[0].usd == pytest.approx(1.1) and r.fixes[2].control == "settings.ai.cloudCaps"


def test_the_scope_is_the_app_when_the_app_cap_is_what_refused(tmp_path, _no_app_caps):
    _no_app_caps[spend.APP_DAILY_KEY] = 0.5
    lib = _project(tmp_path)
    r = _over(lib, 0.6)
    assert (r.kind, r.scope) == ("cap-daily", "app") and "a day" in r.words


def test_the_project_and_run_caps_have_their_own_kinds(tmp_path):
    lib = _project(tmp_path, "cloud_project_cap_usd: 1\n")
    assert _over(lib, 2.0).kind == "cap-project"
    lib2 = _project(tmp_path / "b", "cloud_spend_cap_usd: 100\n")
    spend.set_run_cap(lib2, "run-1", 1.0)
    assert _over(lib2, 2.0).kind == "cap-run"


def test_the_images_refusal_offers_all_four_in_order():
    r = refusal.for_images(project="P", words="x")
    assert _kinds(r) == ["allow-everywhere", "allow-project", "allow-once", "open-settings"]
    assert r.fixes[-1].control == "settings.ai.cloudAllowed" and r.kind == "images"


def test_with_no_project_open_only_the_app_wide_fix_and_settings():
    r = refusal.for_images(project=None, words="x")
    assert _kinds(r) == ["allow-everywhere", "open-settings"] and r.scope == "app"


def test_the_errors_carry_the_refusal(tmp_path):
    err = EgressRefusedError("openai", model="m", project=_project(tmp_path))
    assert err.refusal.kind == "images" and "allow-everywhere" in _kinds(err.refusal)
    lib = _project(tmp_path / "c", "cloud_spend_cap_usd: 0\n")
    with spend._LOCK:
        over = spend._over_cap(lib, 0.0, 0.1)
    assert spend.CloudSpendRefusedError("x", spend.cap_refusal(lib, 0.1, over)).refusal.kind == "cap-monthly"


def test_a_page_failure_and_a_pause_carry_it(tmp_path):
    from fichero_server.execution.runner import _typed_failure

    lib = _project(tmp_path, "cloud_spend_cap_usd: 0\n")
    with spend._LOCK:
        over = spend._over_cap(lib, 0.0, 0.1)
    typed = _typed_failure(spend.CloudSpendRefusedError("x", spend.cap_refusal(lib, 0.1, over)))
    assert typed["category"] == "spend_refused" and typed["refusal"]["kind"] == "cap-monthly"
    egress = _typed_failure(EgressRefusedError("openai", project=lib))
    assert egress["category"] == "egress_refused" and egress["refusal"]["kind"] == "images"
    stop = spend._cap_stop(lib, 0.1, "x")
    assert "refusal" not in stop  # the pause adds it where the run asks to pause (holding())
