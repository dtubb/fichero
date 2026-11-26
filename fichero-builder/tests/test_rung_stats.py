from fichero_builder import rung_stats


def test_rung_stats_means_percentiles_and_since():
    rows = [{"event": "activity", "state": "rung", "rung": "build", "seconds": s, "ts": f"2026-11-0{d}T10:00:00"} for s, d in ((10, 1), (20, 2), (60, 3))]
    rows += [{"event": "activity", "state": "rung", "rung": "guards", "seconds": None, "wall_s": 120.0, "ts": "2026-11-03T10:00:00"}, {"event": "loop"}]
    assert rung_stats.stats(rows)["build"] == {"n": 3, "mean": 30.0, "p90": 60.0, "max": 60.0, "total_min": 1.5}
    assert rung_stats.stats(rows)["guards"]["mean"] == 120.0, "no `seconds`: the wall clock stands"
    assert rung_stats.stats(rows, "2026-11-02")["build"]["n"] == 2


def test_flow_prints_each_target_from_a_fixture_journal_and_exits_1_when_one_is_over(tmp_path, monkeypatch, capsys):
    """local.flow.report: each target of the check flow, measured from the journal alone; exit 1 when any is over."""
    import json
    import types

    from fichero_builder import journal
    rows = []
    for i, mins in enumerate((3, 4, 5)):  # ladder runs of 3, 4 and 5 min
        rows += [{"event": "activity", "kind": "check", "key": f"check {i}", "state": "start", "ts": f"2026-11-26T1{i}:00:00"},
                 {"event": "activity", "kind": "check", "key": f"check {i}", "state": "end", "ts": f"2026-11-26T1{i}:0{mins}:00"}]
    rows += [{"event": "queue", "lane": "l", "step": "1", "state": "done", "ts": "2026-11-26T10:00:00"},
             {"event": "queue", "lane": "l", "step": "1", "state": "done", "ts": "2026-11-26T11:00:00"},
             {"event": "queue", "lane": "l", "step": "1", "state": "landed", "ts": "2026-11-26T11:20:00"},
             {"event": "train", "seconds": 1200, "ts": "2026-11-26T12:00:00"},
             {"event": "lock", "name": "ladder", "state": "clash", "what": "the check of b", "ts": "2026-11-26T12:00:00"},
             {"event": "lock", "name": "ladder", "state": "acquired", "what": "the check of b", "seconds": 300, "ts": "2026-11-26T12:05:00"},
             {"event": "lock", "name": "ladder", "state": "acquired", "what": "the check of c", "seconds": 99, "ts": "2026-11-26T12:05:00"},
             {"event": "activity", "state": "rung", "rung": "ready", "ok": False, "ts": "2026-11-26T12:06:00"}]
    got = {name: (val, ok) for name, val, _limit, ok in rung_stats.flow(rows)}
    assert got["ladder run wall time, median (min)"] == (4.0, True) and got["ladder run wall time, 90th percentile (min)"] == (5.0, True)
    assert got["slot wait for a shared file (s)"] == (300.0, False), "only the wait behind a shared file counts"
    assert got["DONE rows per landed step, mean"] == (2.0, True)
    assert got["last DONE to landed, median (min)"] == (20.0, True) and got["first DONE to landed, median (min)"] == (80.0, True)
    assert got["train wall time, 90th percentile (min)"] == (20.0, True) and got["ready reds inside a ladder"] == (1.0, False)
    assert len(got) == 10
    monkeypatch.setattr(journal, "STATE", tmp_path)
    (tmp_path / "journal.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    (tmp_path / "harness.toml").write_text("[flow]\nready_reds = 1\nshared_file_wait_s = 300\n")
    assert rung_stats.main(types.SimpleNamespace(flow=True, since="", root=str(tmp_path))) == 0, "[flow] moves the targets"
    (tmp_path / "harness.toml").write_text("[flow]\n")
    assert rung_stats.main(types.SimpleNamespace(flow=True, since="", root=str(tmp_path))) == 1
    out = capsys.readouterr().out
    assert "ready reds inside a ladder" in out and " over" in out
