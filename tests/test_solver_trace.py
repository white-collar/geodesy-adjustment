"""Tests for the optional step-by-step trace of adjust()."""

import pytest

from geo_adjust.solver import adjust
from helpers import noiseless_observations, perturbed_points


def test_trace_disabled_by_default():
    points = perturbed_points()
    observations = noiseless_observations()

    result = adjust(points, observations)

    assert result.trace == []


def test_trace_records_expected_steps():
    points = perturbed_points()
    observations = noiseless_observations()

    result = adjust(points, observations, trace=True)

    assert result.trace[0]["step"] == "start"
    assert result.trace[-1]["step"] == "final"

    iteration_steps = result.trace[1:-1]
    assert len(iteration_steps) == result.iterations
    assert [s["step"] for s in iteration_steps] == [f"iteration_{i}" for i in range(1, result.iterations + 1)]

    n_unknowns = 2 * len(result.point_unknown_order) + len(result.orientation_unknown_order)
    first_iter = iteration_steps[0]
    assert len(first_iter["unknown_labels"]) == n_unknowns
    assert len(first_iter["A"]) == len(observations)
    assert len(first_iter["A"][0]) == n_unknowns
    assert len(first_iter["N"]) == n_unknowns
    assert len(first_iter["N"][0]) == n_unknowns
    assert len(first_iter["delta"]) == n_unknowns

    last_iter = iteration_steps[-1]
    assert last_iter["converged"] is True

    final = result.trace[-1]
    final_v = [row["v"] for row in final["residuals"]]
    assert final_v == pytest.approx(list(result.residuals), abs=1e-12)
    assert final["rank"] == result.rank


def test_trace_final_sigma0_is_none_when_not_computable():
    # A minimal, non-redundant network: dof = 0, sigma0 is NaN in the
    # regular result — the trace must report None (JSON-safe), not NaN.
    from geo_adjust import geometry as geo
    from geo_adjust.model import Observation, Point

    A = (0.0, 0.0)
    B = (0.0, 1000.0)
    C = (800.0, 300.0)
    fixed = [Point(id="A", x=A[0], y=A[1], fixed=True), Point(id="B", x=B[0], y=B[1], fixed=True)]
    angle_val = geo.angle(A[0], A[1], B[0], B[1], C[0], C[1])
    obs = [
        Observation("angle", "A", "B", angle_val, 3e-6, to_id2="C"),
        Observation("distance", "A", "C", geo.distance(*A, *C), 0.005),
    ]
    points2 = fixed + [Point(id="C", x=790.0, y=310.0, fixed=False)]

    result = adjust(points2, obs, trace=True)

    assert result.sigma0 != result.sigma0  # NaN
    assert result.trace[-1]["sigma0"] is None
