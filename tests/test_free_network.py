"""Free network (no fixed points): normal matrix N is singular, solver must
fall back to the pseudo-inverse and still recover the network's shape.

Absolute coordinates are not observable in a free network (they float with
whatever minimum-norm datum the pseudo-inverse picks), so correctness is
checked via pairwise coordinate differences, which are invariant to the
network's unresolved translation.
"""

import itertools

import pytest

from geo_adjust.solver import adjust
from helpers import TRUE_COORDS, noiseless_observations, perturbed_points


def test_free_network_recovers_shape():
    points = perturbed_points(dx=10.0, dy=-15.0, fixed_ids=set())
    observations = noiseless_observations()

    result = adjust(points, observations)

    assert result.converged
    n_unknowns = 2 * len(result.point_unknown_order)
    assert result.rank < n_unknowns  # datum is genuinely underdetermined
    assert result.residuals == pytest.approx(0.0, abs=1e-8)

    for (p, q) in itertools.combinations(TRUE_COORDS, 2):
        true_dx = TRUE_COORDS[q][0] - TRUE_COORDS[p][0]
        true_dy = TRUE_COORDS[q][1] - TRUE_COORDS[p][1]
        xp, yp = result.coords[p]
        xq, yq = result.coords[q]
        assert (xq - xp) == pytest.approx(true_dx, abs=1e-6)
        assert (yq - yp) == pytest.approx(true_dy, abs=1e-6)
