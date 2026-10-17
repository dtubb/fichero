"""Greenhouse gas is an estimate from energy x grid intensity, and always says its basis (#5420,
`activity.ghg.estimate-with-its-basis`): measured power, rated power, or unknown -- never invented."""
from __future__ import annotations

from fichero_server.execution.ghg import estimate, roll_up


def test_measured_power_over_the_jobs_time_times_the_grid_intensity():
    # 40 W for one hour = 0.04 kWh; at 500 g/kWh = 20 g.
    assert estimate(power_watts=40, seconds=3600, grid_g_per_kwh=500, measured=True) == {"grams": 20.0, "basis": "measured"}


def test_a_rated_power_is_an_estimate():
    assert estimate(power_watts=300, seconds=1800, grid_g_per_kwh=400, measured=False) == {"grams": 60.0, "basis": "estimate"}


def test_a_missing_power_or_grid_figure_is_unknown_never_zero():
    unknown = {"grams": None, "basis": "unknown"}
    assert estimate(power_watts=None, seconds=60, grid_g_per_kwh=400, measured=True) == unknown
    assert estimate(power_watts=40, seconds=60, grid_g_per_kwh=None, measured=True) == unknown
    assert estimate(power_watts=40, seconds=None, grid_g_per_kwh=400, measured=True) == unknown


def test_a_roll_up_sums_what_is_known_and_takes_the_weakest_basis():
    parts = [
        {"grams": 20.0, "basis": "measured"},
        {"grams": 60.0, "basis": "estimate"},
        {"grams": None, "basis": "unknown"},
    ]
    assert roll_up(parts) == {"grams": 80.0, "basis": "estimate", "unknown_parts": 1}
    assert roll_up([{"grams": 20.0, "basis": "measured"}]) == {"grams": 20.0, "basis": "measured", "unknown_parts": 0}


def test_a_roll_up_of_nothing_known_is_unknown():
    assert roll_up([]) == {"grams": None, "basis": "unknown", "unknown_parts": 0}
    assert roll_up([{"grams": None, "basis": "unknown"}]) == {"grams": None, "basis": "unknown", "unknown_parts": 1}
