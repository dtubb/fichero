"""`scripts/soak_run.py` (`runner.soak.drives-the-real-engine`, #6732): its readings, its verdict, and its kill-and-resume loop with a
fake engine. No engine, no model, no network."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "soak_run.py"
_SPEC = importlib.util.spec_from_file_location("soak_run", _SCRIPT)
assert _SPEC and _SPEC.loader
sr = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = sr
_SPEC.loader.exec_module(sr)  # type: ignore[attr-defined]

PS = "  1     0  1000\n 10     1  2048000\n 11    10  1024000\n 12     1  5000\n 13    11   512000\n"


def _status(done, total=100, failed=0, state="running", kinds=None, loads=0):
    return {"state": state, "steps": [{"account": {"pages_done": done, "pages_failed": failed, "pages_left": total - done - failed,
                                                    "pages_total": total}, "failures_by_kind": kinds or {}, "model_loads": loads}]}


def _samples(dones, rss=None, total=100, last_state="done"):
    out, prev = [], None
    for i, d in enumerate(dones):
        st = last_state if i == len(dones) - 1 else "running"
        prev = sr.reading(_status(d, total, state=st), minute=i, rss_mb=(rss or [1000] * len(dones))[i], swap_mb=0.0, previous=prev)
        out.append(prev)
    return out


def test_rss_counts_the_engine_and_every_descendant_and_nothing_else():
    assert sr.tree_rss_mb(PS, 10) == round((2048000 + 1024000 + 512000) / 1024, 1)


def test_swap_used_is_read_in_mb():
    assert sr.parse_swap_mb("total = 2048.00M  used = 1023.25M  free = 1024.75M  (encrypted)") == 1023.2
    assert sr.parse_swap_mb("total = 4.00G  used = 2.00G") == 2048.0
    assert sr.parse_swap_mb("garbage") is None


def test_a_reading_has_pages_per_hour_failures_by_kind_and_loads():
    first = sr.reading(_status(10), minute=1, rss_mb=900, swap_mb=1.0, previous=None)
    second = sr.reading(_status(40, kinds={"memory": 2}, loads=3), minute=2, rss_mb=950, swap_mb=1.0, previous=first)
    assert second["pages_per_hour"] == 1800.0 and second["failures_by_kind"] == {"memory": 2} and second["model_loads"] == 3


def test_a_clean_run_is_ok():
    v = sr.judge(_samples([0, 20, 40, 60, 80, 100]), 100, resume=None)
    assert v["ok"] and v["reds"] == []


def test_a_count_that_falls_is_pages_lost():
    v = sr.judge(_samples([0, 50, 30, 100]), 100, resume=None)
    assert not v["ok"] and any("lost" in r for r in v["reds"])


def test_more_done_than_pages_is_a_page_done_twice():
    s = _samples([0, 50, 100])
    s[1]["accounts"][0]["pages_done"] = 120
    assert any("done twice" in r for r in sr.judge(s, 100, resume=None)["reds"])


def test_a_run_that_ends_done_with_pages_neither_read_nor_failed_lost_them():
    v = sr.judge(_samples([0, 50, 90]), 100, resume=None)
    assert any("pages were lost" in r for r in v["reds"])


def test_memory_that_keeps_growing_after_warm_up_is_a_leak():
    rss = [1000 + 50 * i for i in range(40)]  # 50 MB a minute = 3000 MB/hour
    v = sr.judge(_samples(list(range(0, 400, 10)), rss=rss, total=400), 400, resume=None)
    assert any("a leak" in r for r in v["reds"]) and v["leak_mb_per_hour"] > sr.LEAK_MB_PER_HOUR


def test_flat_memory_is_no_leak():
    v = sr.judge(_samples(list(range(0, 401, 10)), rss=[2000] * 41, total=400), 400, resume=None)
    assert v["leak_mb_per_hour"] == 0 and v["ok"], v["reds"]


def test_a_peak_over_the_bound_is_red():
    v = sr.judge(_samples([0, 50, 100], rss=[1000, sr.RSS_BOUND_MB + 1, 1000]), 100, resume=None)
    assert any("bound" in r for r in v["reds"])


def test_5000_pages_over_ten_hours_is_red_and_under_is_not():
    slow = _samples([0, 100], total=100)
    slow[-1]["minute"] = 600.0  # 100 pages in 10 h: 5000 would take 500 h
    assert any("5000 pages would take" in r for r in sr.judge(slow, 100, resume=None)["reds"])
    fast = _samples([0, 100], total=100)
    fast[-1]["minute"] = 60.0  # 100 an hour: 50 h... still over
    assert sr.projected_hours(fast) == 50.0
    fast[-1]["minute"] = 1.0  # 6000 an hour
    assert sr.judge(fast, 100, resume=None)["ok"]


def test_the_time_the_engine_was_down_is_not_counted_against_the_rate():
    s = _samples([0, 100])
    s[-1]["minute"] = 60.0
    assert sr.projected_hours(s, down_minutes=30.0) == 25.0


def test_resume_with_fewer_pages_done_is_pages_lost_and_with_more_is_fine():
    assert "lost" in sr.resume_check({"done": 50}, {"done": 45})["problem"]
    assert sr.resume_check({"done": 50}, {"done": 50})["problem"] is None


class FakeEngine:
    def __init__(self, dones, total=100):
        self.dones, self.total, self.log, self.after_restart = list(dones), total, [], None

    def status(self, _job):
        return _status(self.dones.pop(0), self.total, state="done" if len(self.dones) == 0 else "running")

    def rss_mb(self):
        return 1000.0

    def kill(self):
        self.log.append("kill")

    def start(self):
        self.log.append("start")


def test_kill_at_kills_once_restarts_and_checks_the_run_carried_on(monkeypatch):
    monkeypatch.setattr(sr, "sh", lambda _a: "")
    engine = FakeEngine([10, 40, 40, 70, 100])  # the 40 after the restart is the resumed count
    got = sr.soak(engine, "job", 100, kill_at=40, every=0, hours=1, sleep=lambda _s: None)
    assert engine.log == ["kill", "start"] and got["resume"]["problem"] is None
    assert sr.judge(got["samples"], 100, resume=got["resume"], down_minutes=got["down_minutes"])["ok"]


def test_a_restart_that_loses_pages_fails_the_soak(monkeypatch):
    monkeypatch.setattr(sr, "sh", lambda _a: "")
    engine = FakeEngine([10, 40, 5, 60, 100])
    got = sr.soak(engine, "job", 100, kill_at=40, every=0, hours=1, sleep=lambda _s: None)
    v = sr.judge(got["samples"], 100, resume=got["resume"])
    assert not v["ok"] and any("lost" in r for r in v["reds"])


def test_the_google_dry_cost_is_per_1000_pages_and_unknown_when_a_model_has_no_price():
    assert sr.cost_per_1000({"cloud_cap": {"estimate_usd": 1.5}}, 300) == {"pages": 300, "estimate_usd": 1.5, "usd_per_1000": 5.0}
    assert sr.cost_per_1000({"cloud_cap": {"estimate_usd": None}}, 300)["usd_per_1000"] is None
    assert sr.cost_per_1000({}, 300)["usd_per_1000"] is None


def test_the_markdown_names_the_verdict_and_every_reading():
    s = _samples([0, 50, 100])
    report = {"pages": 100, "steps": "segment", "place": "local", "samples": s, "resume": None, "cost": None,
              "verdict": sr.judge(s, 100, resume=None)}
    text = sr.markdown(report)
    assert "verdict: **ok**" in text and text.count("\n| ") >= 3


class FakeCli:
    """The fichero CLI of a scratch library whose project has no recipe yet: Start refuses a step the saved recipe lacks."""

    RECIPES = {"transcribe": ["find-lines", "leave-out", "read-a-line"], "tables": ["find-regions", "find-lines", "read-a-line"]}

    def __init__(self):
        self.saved, self.calls = None, []

    def __call__(self, *args):
        self.calls.append(args)
        if args[:2] == ("recipes", "assemble"):
            purpose = args[args.index("--purposes") + 1]
            return {"steps": [{"id": i, "job": i} for i in self.RECIPES[purpose]]}
        if args[:2] == ("recipes", "save-project-setup"):
            import json as _json
            self.saved = _json.loads(args[args.index("--recipe") + 1])
            return {}
        if args[:2] == ("recipes", "start-project"):
            have = {s["id"] for s in (self.saved or {}).get("steps") or []}
            missing = [a for a in args[2:] if a != "--steps" and a not in have]
            if missing:
                raise RuntimeError(f"POST /api/recipes/project/start -> 422: the recipe has no step {', '.join(missing)}")
            return {"started": {"job_id": "j1"}}
        return {}


def _engine_with(cli, tmp_path):
    engine = sr.Engine.__new__(sr.Engine)
    engine.cli = cli
    engine.library = tmp_path / "Soak.fichero"
    return engine


def test_start_run_saves_a_recipe_that_has_the_asked_step_first(tmp_path):
    cli = FakeCli()
    engine = _engine_with(cli, tmp_path)
    engine.save_recipe("segment", "local")
    assert engine.start_run("segment")["started"]["job_id"] == "j1"


def test_a_step_only_another_recipe_has_picks_that_recipe(tmp_path):
    cli = FakeCli()
    engine = _engine_with(cli, tmp_path)
    engine.save_recipe("regions", "local")
    assert engine.start_run("regions")["started"]["job_id"] == "j1"
    assert "find-regions" in {s["id"] for s in cli.saved["steps"]}


def test_a_step_no_recipe_has_stops_the_soak_in_words(tmp_path):
    import pytest

    cli = FakeCli()
    cli.RECIPES = {"transcribe": ["find-lines"], "tables": ["find-lines"]}
    engine = _engine_with(cli, tmp_path)
    with pytest.raises(RuntimeError, match="find-regions"):
        engine.save_recipe("regions", "local")


def test_page_images_walk_subfolders_and_skip_packages_and_thumbnails(tmp_path):
    for rel in ("a.png", "box1/b.JPG", "box1/sub/c.tif", "Old.fichero/pages/d.png", "thumbnails/e.png", "box1/notes.txt"):
        f = tmp_path / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(b"x")
    assert [p.relative_to(tmp_path).as_posix() for p in sr.page_images(tmp_path, None)] == ["a.png", "box1/b.JPG", "box1/sub/c.tif"]
    assert len(sr.page_images(tmp_path, 2)) == 2


def test_swap_is_read_with_sysctl_by_absolute_path(monkeypatch):
    seen = []
    monkeypatch.setattr(sr, "sh", lambda argv: seen.append(argv) or "")
    sr.soak(FakeEngine([100]), "job", 100, kill_at=None, every=0, hours=1, sleep=lambda _s: None)
    assert ["/usr/sbin/sysctl", "-n", "vm.swapusage"] in seen


# ── runner-soak soak-3: a run that ends badly or stops moving ends the soak (#6732) ──────────────────────────


def test_a_run_that_ends_failed_or_cancelled_is_red_whatever_its_pages():
    for state in ("failed", "cancelled"):
        v = sr.judge(_samples([10, 40], last_state=state), 100, resume=None)
        assert not v["ok"] and any(state in r for r in v["reds"]), v


class StuckEngine(FakeEngine):
    """Pages done never move (a run paused or stalled): the soak must give up by itself."""

    def status(self, _job):
        return _status(40, self.total, state="paused")


def test_no_progress_for_five_minutes_ends_the_soak_red_instead_of_polling_on(monkeypatch):
    monkeypatch.setattr(sr, "sh", lambda _a: "")
    now = [0.0]

    def clock():
        return now[0]

    def sleep(seconds):
        now[0] += seconds

    got = sr.soak(StuckEngine([]), "job", 100, kill_at=None, every=60, hours=14, clock=clock, sleep=sleep)
    assert got["samples"][-1]["minute"] <= 6.1, "the soak polled past five minutes of no progress"
    v = sr.judge(got["samples"], 100, resume=None, stalled=got["stalled"])
    assert got["stalled"] and not v["ok"] and any("no progress" in r for r in v["reds"]), v


def test_a_run_that_keeps_moving_is_never_called_stalled(monkeypatch):
    monkeypatch.setattr(sr, "sh", lambda _a: "")
    now = [0.0]
    got = sr.soak(FakeEngine(list(range(0, 100, 5)) + [100]), "job", 100, kill_at=None, every=240, hours=14,
                  clock=lambda: now[0], sleep=lambda s: now.__setitem__(0, now[0] + s))
    assert not got["stalled"]


def test_files_with_the_same_name_from_different_folders_get_unique_upload_names(tmp_path):
    pages = []
    for rel in ("box1/001.png", "box2/001.png", "box2/002.png", "box1/sub/001.png"):
        f = tmp_path / "src" / rel
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(rel.encode())
        pages.append(f)
    ups = sr.unique_uploads(pages, tmp_path / "up")
    names = [u.name for u in ups]
    assert len(set(names)) == 4 and "002.png" in names
    assert [u.read_bytes() for u in ups] == [p.read_bytes() for p in pages]
