"""Direction observations: verify the per-station orientation unknown Z is
modeled with the right sign and recovered correctly alongside coordinates.
"""

import math

import pytest

from geo_adjust import geometry as geo
from geo_adjust.model import Observation
from geo_adjust.solver import adjust
from helpers import TRUE_COORDS, noiseless_observations, perturbed_points

Z_TRUE = 0.37  # arbitrary instrument-zero offset at station C, radians
DIRECTION_TARGETS = ["A", "D", "E"]
SIGMA_DIR = 3e-6


def _direction_observations():
    xi, yi = TRUE_COORDS["C"]
    obs = []
    for target in DIRECTION_TARGETS:
        xj, yj = TRUE_COORDS[target]
        az = geo.azimuth(xi, yi, xj, yj)
        value = geo.wrap_angle(az - Z_TRUE)
        obs.append(Observation("direction", "C", target, value, SIGMA_DIR))
    return obs


def test_recovers_coordinates_and_orientation():
    points = perturbed_points(dx=20.0, dy=-10.0)
    observations = noiseless_observations() + _direction_observations()

    result = adjust(points, observations)

    assert result.converged
    for pid, (true_x, true_y) in TRUE_COORDS.items():
        if pid in {"A", "B"}:
            continue
        x, y = result.coords[pid]
        assert x == pytest.approx(true_x, abs=1e-6)
        assert y == pytest.approx(true_y, abs=1e-6)

    assert "C" in result.orientation_unknown_order
    assert result.orientations["C"] == pytest.approx(Z_TRUE, abs=1e-6)
    assert result.residuals == pytest.approx(0.0, abs=1e-8)
