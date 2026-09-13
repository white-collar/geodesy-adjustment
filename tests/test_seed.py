"""Tests for automatic approximate-coordinate computation (geo_adjust/seed.py)."""

import math

import pytest

from geo_adjust import geometry as geo
from geo_adjust.model import Observation, Point
from geo_adjust.seed import compute_initial_coordinates
from geo_adjust.solver import adjust

A = (0.0, 0.0)
B = (0.0, 1000.0)
C = (800.0, 300.0)
D = (900.0, 900.0)


def test_distance_azimuth_chain():
    # A is fixed; a single azimuth+distance leg reaches C directly.
    fixed = [Point(id="A", x=A[0], y=A[1], fixed=True)]
    observations = [
        Observation("azimuth", "A", "C", geo.azimuth(*A, *C), 3e-6),
        Observation("distance", "A", "C", geo.distance(*A, *C), 0.005),
    ]

    coords, unresolved = compute_initial_coordinates(fixed, observations)

    assert unresolved == []
    assert coords["C"] == pytest.approx(C, abs=1e-9)


def test_angle_turning_chain():
    # A, B fixed (so az(A,B) is derivable from coordinates alone, no
    # azimuth instrument reading needed). An angle at A turning from B to C
    # plus a distance A-C should resolve C, mirroring a real traverse tie-in.
    fixed = [
        Point(id="A", x=A[0], y=A[1], fixed=True),
        Point(id="B", x=B[0], y=B[1], fixed=True),
    ]
    angle_value = geo.angle(A[0], A[1], B[0], B[1], C[0], C[1])
    observations = [
        Observation("angle", "A", "B", angle_value, 3e-6, to_id2="C"),
        Observation("distance", "A", "C", geo.distance(*A, *C), 0.005),
    ]

    coords, unresolved = compute_initial_coordinates(fixed, observations)

    assert unresolved == []
    assert coords["C"] == pytest.approx(C, abs=1e-9)


def test_multi_leg_traverse():
    # A fixed with an azimuth+distance leg to C, then a turned angle at C
    # (from A to D) plus a distance C-D reaches D two legs deep.
    fixed = [Point(id="A", x=A[0], y=A[1], fixed=True)]
    angle_at_c = geo.angle(C[0], C[1], A[0], A[1], D[0], D[1])
    observations = [
        Observation("azimuth", "A", "C", geo.azimuth(*A, *C), 3e-6),
        Observation("distance", "A", "C", geo.distance(*A, *C), 0.005),
        Observation("angle", "C", "A", angle_at_c, 3e-6, to_id2="D"),
        Observation("distance", "C", "D", geo.distance(*C, *D), 0.005),
    ]

    coords, unresolved = compute_initial_coordinates(fixed, observations)

    assert unresolved == []
    assert coords["C"] == pytest.approx(C, abs=1e-9)
    assert coords["D"] == pytest.approx(D, abs=1e-9)


def test_direction_calibration():
    # Station C takes two direction (limb) readings, to A and to D, on an
    # arbitrary instrument zero. Neither leg alone gives an absolute
    # azimuth, but once the A-leg is calibrated against the already-known
    # az(C,A) (both C and A being resolvable via the first two
    # observations), the D-leg should resolve too.
    fixed = [Point(id="A", x=A[0], y=A[1], fixed=True)]
    z_true = 1.234
    az_ca = geo.azimuth(*C, *A)
    az_cd = geo.azimuth(*C, *D)
    observations = [
        Observation("azimuth", "A", "C", geo.azimuth(*A, *C), 3e-6),
        Observation("distance", "A", "C", geo.distance(*A, *C), 0.005),
        Observation("direction", "C", "A", geo.wrap_angle(az_ca - z_true), 3e-6),
        Observation("direction", "C", "D", geo.wrap_angle(az_cd - z_true), 3e-6),
        Observation("distance", "C", "D", geo.distance(*C, *D), 0.005),
    ]

    coords, unresolved = compute_initial_coordinates(fixed, observations)

    assert unresolved == []
    assert coords["D"] == pytest.approx(D, abs=1e-9)


def test_isolated_point_is_reported_unresolved():
    fixed = [Point(id="A", x=A[0], y=A[1], fixed=True)]
    observations = [
        Observation("azimuth", "A", "C", geo.azimuth(*A, *C), 3e-6),
        Observation("distance", "A", "C", geo.distance(*A, *C), 0.005),
        # X and D only ever appear in a plain distance observation between
        # each other: no azimuth/angle ever gives their orientation, and
        # neither is reachable from the fixed point A.
        Observation("distance", "X", "D", 500.0, 0.005),
    ]

    coords, unresolved = compute_initial_coordinates(fixed, observations)

    assert "C" in coords
    assert set(unresolved) == {"D", "X"}


def test_single_reference_point_without_bearing_gets_arbitrary_orientation():
    # Only A is fixed, and there is no azimuth/direction anywhere: rotation
    # around A is genuinely undetermined, but shape/scale are not (distances
    # and the turned angle fully constrain them) — seed.py should still
    # resolve everyone by picking one arbitrary bearing, exactly like a
    # surveyor conventionally assigning a "условный" bearing to one line.
    fixed = [Point(id="A", x=A[0], y=A[1], fixed=True)]
    dist_ac = geo.distance(*A, *C)
    angle_at_c = geo.angle(C[0], C[1], A[0], A[1], D[0], D[1])
    dist_cd = geo.distance(*C, *D)
    observations = [
        Observation("distance", "A", "C", dist_ac, 0.005),
        Observation("angle", "C", "A", angle_at_c, 3e-6, to_id2="D"),
        Observation("distance", "C", "D", dist_cd, 0.005),
    ]

    coords, unresolved = compute_initial_coordinates(fixed, observations)

    assert unresolved == []
    xa, ya = coords["A"]
    xc, yc = coords["C"]
    xd, yd = coords["D"]
    # Shape/scale must be exactly right even though absolute orientation is
    # arbitrary: distances and the turned angle come back unchanged.
    assert geo.distance(xa, ya, xc, yc) == pytest.approx(dist_ac, abs=1e-9)
    assert geo.distance(xc, yc, xd, yd) == pytest.approx(dist_cd, abs=1e-9)
    assert geo.angle(xc, yc, xa, ya, xd, yd) == pytest.approx(angle_at_c, abs=1e-9)


def test_distance_only_point_still_needs_resection_even_after_orientation_fix():
    # A fixed; distance(A,C) gets unstuck by the synthetic bearing, but E is
    # tied to A only by a plain distance with no angle anywhere near it —
    # the one-time injection must not paper over a genuine resection case.
    fixed = [Point(id="A", x=A[0], y=A[1], fixed=True)]
    observations = [
        Observation("distance", "A", "C", geo.distance(*A, *C), 0.005),
        Observation("distance", "A", "E", 500.0, 0.005),
    ]

    coords, unresolved = compute_initial_coordinates(fixed, observations)

    assert "C" in coords
    assert "E" not in coords
    assert unresolved == ["E"]


def test_no_synthetic_orientation_when_a_real_bearing_exists():
    # A real azimuth exists (A-C), so resolved_azimuth is not empty: Q, tied
    # to A only by a plain distance elsewhere in the graph, genuinely needs
    # resection and must stay unresolved rather than get a fabricated
    # direction just because *some* real bearing exists in the dataset.
    fixed = [Point(id="A", x=A[0], y=A[1], fixed=True)]
    observations = [
        Observation("azimuth", "A", "C", geo.azimuth(*A, *C), 3e-6),
        Observation("distance", "A", "C", geo.distance(*A, *C), 0.005),
        Observation("distance", "A", "Q", 700.0, 0.005),
    ]

    coords, unresolved = compute_initial_coordinates(fixed, observations)

    assert coords["C"] == pytest.approx(C, abs=1e-9)
    assert "Q" not in coords
    assert unresolved == ["Q"]


def test_fully_free_network_gets_synthetic_anchor_and_adjusts_to_correct_shape():
    fixed: list[Point] = []
    observations = [
        Observation("azimuth", "A", "C", geo.azimuth(*A, *C), 3e-6),
        Observation("distance", "A", "C", geo.distance(*A, *C), 0.005),
        Observation("distance", "A", "D", geo.distance(*A, *D), 0.005),
        Observation("angle", "A", "C", geo.angle(A[0], A[1], C[0], C[1], D[0], D[1]), 3e-6, to_id2="D"),
    ]

    coords, unresolved = compute_initial_coordinates(fixed, observations)
    assert unresolved == []

    points = [Point(id=pid, x=x, y=y, fixed=False) for pid, (x, y) in coords.items()]
    result = adjust(points, observations)

    assert result.converged
    ax, ay = result.coords["A"]
    cx, cy = result.coords["C"]
    dx, dy = result.coords["D"]
    assert (cx - ax, cy - ay) == pytest.approx((C[0] - A[0], C[1] - A[1]), abs=1e-6)
    assert (dx - ax, dy - ay) == pytest.approx((D[0] - A[0], D[1] - A[1]), abs=1e-6)
