"""Cross-check analytic partial derivatives against central finite differences.

This is the primary defense against sign errors in the Jacobian formulas
(the main correctness risk for the whole solver).
"""

import numpy as np
import pytest

from geo_adjust import geometry as geo

H = 1e-6
TOL = 1e-6

RNG = np.random.default_rng(42)


def _random_points(n, scale=1000.0):
    return [tuple(RNG.uniform(-scale, scale, size=2)) for _ in range(n)]


def _numeric_partial(f, args, k):
    plus = list(args)
    minus = list(args)
    plus[k] += H
    minus[k] -= H
    return (f(*plus) - f(*minus)) / (2 * H)


@pytest.mark.parametrize("trial", range(10))
def test_distance_partials(trial):
    (xi, yi), (xj, yj) = _random_points(2)
    args = (xi, yi, xj, yj)
    analytic = geo.distance_partials(*args)
    for k in range(4):
        numeric = _numeric_partial(geo.distance, args, k)
        assert analytic[k] == pytest.approx(numeric, abs=TOL)


@pytest.mark.parametrize("trial", range(10))
def test_azimuth_partials(trial):
    (xi, yi), (xj, yj) = _random_points(2)
    args = (xi, yi, xj, yj)
    analytic = geo.azimuth_partials(*args)
    for k in range(4):
        numeric = _numeric_partial(geo.azimuth, args, k)
        assert analytic[k] == pytest.approx(numeric, abs=TOL)


@pytest.mark.parametrize("trial", range(10))
def test_angle_partials(trial):
    (xi, yi), (xj, yj), (xk, yk) = _random_points(3)
    args = (xi, yi, xj, yj, xk, yk)
    analytic = geo.angle_partials(*args)
    for k in range(6):
        numeric = _numeric_partial(geo.angle, args, k)
        assert analytic[k] == pytest.approx(numeric, abs=TOL)
