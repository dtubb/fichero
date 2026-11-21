"""Kraken 7.1.1 calls `np.cross` on 2-D vectors for a baseline with more than two points; numpy 2.5 raises, kraken swallows
the error and returns an empty reading (#6750). The engine gives `kraken.lib.segmentation` a 2-D cross product."""
import sys
import types

import numpy as np
import pytest

from fichero_server.llm import kraken_runtime


@pytest.fixture
def fake_kraken_segmentation(monkeypatch):
    """A stand-in for kraken's module: the extractor crosses 2-D vectors for a curved baseline and, like kraken, swallows
    any error into an empty result."""
    segmentation = types.ModuleType("kraken.lib.segmentation")
    segmentation.np = np

    def calculate_polygonal_environment(baselines):
        polygons = []
        for baseline in baselines:
            try:
                points = segmentation.np.asarray(baseline, dtype=float)
                step = segmentation.np.diff(points, axis=0)
                side = segmentation.np.cross(step[:-1], step[1:])  # 2-D vectors: the z of the 3-D cross
                polygons.append(points.tolist() if len(side) else None)
            except Exception:
                polygons.append(None)
        return polygons

    segmentation.calculate_polygonal_environment = calculate_polygonal_environment
    lib = types.ModuleType("kraken.lib")
    lib.segmentation = segmentation
    kraken = types.ModuleType("kraken")
    kraken.lib = lib
    for name, module in (("kraken", kraken), ("kraken.lib", lib), ("kraken.lib.segmentation", segmentation)):
        monkeypatch.setitem(sys.modules, name, module)
    return segmentation


def test_a_curved_baseline_line_is_read_not_empty(fake_kraken_segmentation):
    curved = [[0, 0], [10, 3], [20, 4], [30, 2]]  # more than two points
    assert kraken_runtime.calculate_polygonal_environment([curved]) == [curved]


def test_the_2d_cross_is_the_z_of_the_3d_cross_and_3d_vectors_are_untouched(fake_kraken_segmentation):
    kraken_runtime.calculate_polygonal_environment([[[0, 0], [1, 0], [1, 1]]])
    cross = fake_kraken_segmentation.np.cross
    assert cross(np.array([[1.0, 0.0]]), np.array([[0.0, 1.0]])).tolist() == [1.0]
    assert cross([1, 0, 0], [0, 1, 0]).tolist() == [0, 0, 1]
    assert fake_kraken_segmentation.np.zeros(2).tolist() == [0.0, 0.0]  # everything else is numpy's own
