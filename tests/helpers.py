"""Shared synthetic network used by the solver-level tests."""

from typing import Dict, List, Tuple

from geo_adjust import geometry as geo
from geo_adjust.model import Observation, Point

SIGMA_DIST = 0.005  # meters
SIGMA_ANG = 3e-6  # radians (~0.6 arcsec)

TRUE_COORDS: Dict[str, Tuple[float, float]] = {
    "A": (0.0, 0.0),
    "B": (0.0, 1000.0),
    "C": (800.0, 300.0),
    "D": (900.0, 900.0),
    "E": (400.0, 700.0),
}
FIXED_IDS = {"A", "B"}

DISTANCE_PAIRS = [
    ("A", "C"), ("A", "D"), ("A", "E"),
    ("B", "C"), ("B", "D"), ("B", "E"),
    ("C", "D"), ("D", "E"), ("C", "E"),
]
AZIMUTH_OBS = [("A", "C"), ("B", "E")]
ANGLE_OBS = [("C", "A", "D"), ("D", "C", "B")]  # (station, ray1_target, ray2_target)


def true_points(fixed_ids=FIXED_IDS) -> List[Point]:
    return [
        Point(id=pid, x=x, y=y, fixed=(pid in fixed_ids))
        for pid, (x, y) in TRUE_COORDS.items()
    ]


def noiseless_observations() -> List[Observation]:
    obs: List[Observation] = []
    for i, j in DISTANCE_PAIRS:
        xi, yi = TRUE_COORDS[i]
        xj, yj = TRUE_COORDS[j]
        obs.append(Observation("distance", i, j, geo.distance(xi, yi, xj, yj), SIGMA_DIST))
    for i, j in AZIMUTH_OBS:
        xi, yi = TRUE_COORDS[i]
        xj, yj = TRUE_COORDS[j]
        obs.append(Observation("azimuth", i, j, geo.azimuth(xi, yi, xj, yj), SIGMA_ANG))
    for station, j, k in ANGLE_OBS:
        xi, yi = TRUE_COORDS[station]
        xj, yj = TRUE_COORDS[j]
        xk, yk = TRUE_COORDS[k]
        value = geo.angle(xi, yi, xj, yj, xk, yk)
        obs.append(Observation("angle", station, j, value, SIGMA_ANG, to_id2=k))
    return obs


def perturbed_points(dx: float = 50.0, dy: float = -30.0, fixed_ids=FIXED_IDS) -> List[Point]:
    """Free points shifted from truth; fixed points stay exact."""
    pts = []
    for pid, (x, y) in TRUE_COORDS.items():
        if pid in fixed_ids:
            pts.append(Point(id=pid, x=x, y=y, fixed=True))
        else:
            pts.append(Point(id=pid, x=x + dx, y=y + dy, fixed=False))
    return pts
