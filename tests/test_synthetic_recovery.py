"""Noiseless synthetic network: the solver must exactly recover true coordinates."""

import pytest

from geo_adjust.solver import adjust
from helpers import TRUE_COORDS, noiseless_observations, perturbed_points


def test_recovers_true_coordinates():
    points = perturbed_points(dx=50.0, dy=-30.0)
    observations = noiseless_observations()

    result = adjust(points, observations)

    assert result.converged
    for pid, (true_x, true_y) in TRUE_COORDS.items():
        if pid not in result.coords or pid in {"A", "B"}:
            continue
        x, y = result.coords[pid]
        assert x == pytest.approx(true_x, abs=1e-6)
        assert y == pytest.approx(true_y, abs=1e-6)

    assert result.residuals == pytest.approx(0.0, abs=1e-8)
