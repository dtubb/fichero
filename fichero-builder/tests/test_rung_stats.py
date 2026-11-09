from fichero_builder import rung_stats


def test_rung_stats_means_percentiles_and_since():
    rows = [{"event": "activity", "state": "rung", "rung": "build", "seconds": s, "ts": f"2026-11-0{d}T10:00:00"} for s, d in ((10, 1), (20, 2), (60, 3))]
    rows += [{"event": "activity", "state": "rung", "rung": "guards", "seconds": None, "wall_s": 120.0, "ts": "2026-11-03T10:00:00"}, {"event": "loop"}]
    assert rung_stats.stats(rows)["build"] == {"n": 3, "mean": 30.0, "p90": 60.0, "max": 60.0, "total_min": 1.5}
    assert rung_stats.stats(rows)["guards"]["mean"] == 120.0, "no `seconds`: the wall clock stands"
    assert rung_stats.stats(rows, "2026-11-02")["build"]["n"] == 2
