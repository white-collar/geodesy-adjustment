"""Synthetic network with realistic noise: statistical sanity checks."""

import copy

import numpy as np

from geo_adjust.accuracy import point_accuracies
from geo_adjust.solver import adjust
from helpers import TRUE_COORDS, noiseless_observations, perturbed_points

RNG = np.random.default_rng(7)


def _add_noise(observations):
    noisy = copy.deepcopy(observations)
    for obs in noisy:
        obs.value += RNG.normal(0.0, obs.sigma)
    return noisy


def test_sigma0_near_one_and_coords_within_confidence():
    points = perturbed_points(dx=5.0, dy=-3.0)
    observations = _add_noise(noiseless_observations())

    result = adjust(points, observations)
    accuracies = point_accuracies(result)

    assert result.converged
    # dof = 13 obs - 6 unknowns = 7; sigma0^2 ~ chi2(7)/7, loose bound to avoid flakiness.
    assert 0.15 < result.sigma0 < 4.0

    for pid, (true_x, true_y) in TRUE_COORDS.items():
        if pid not in accuracies:
            continue
        x, y = result.coords[pid]
        acc = accuracies[pid]
        # generous multiple of sigma (not a tight 95% test) to keep this robust.
        assert abs(x - true_x) < 6 * acc.sigma_x
        assert abs(y - true_y) < 6 * acc.sigma_y
