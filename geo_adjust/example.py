"""End-to-end demo: adjust a small synthetic 2D network and print a report.

Run with: python -m geo_adjust.example
"""

import math

import numpy as np

from . import geometry as geo
from .accuracy import orientation_accuracies, point_accuracies
from .model import Observation, Point
from .solver import adjust

TRUE_COORDS = {
    "A": (0.0, 0.0),
    "B": (0.0, 1000.0),
    "C": (800.0, 300.0),
    "D": (900.0, 900.0),
    "E": (400.0, 700.0),
}
FIXED_IDS = {"A", "B"}
SIGMA_DIST = 0.005
SIGMA_ANG = 3e-6

DISTANCE_PAIRS = [
    ("A", "C"), ("A", "D"), ("A", "E"),
    ("B", "C"), ("B", "D"), ("B", "E"),
    ("C", "D"), ("D", "E"), ("C", "E"),
]
AZIMUTH_OBS = [("A", "C"), ("B", "E")]
ANGLE_OBS = [("C", "A", "D"), ("D", "C", "B")]
DIRECTION_OBS = [("D", "A"), ("D", "C"), ("D", "E")]  # station D, arbitrary limb zero
Z_TRUE_D = 1.1781  # radians, instrument-zero offset at station D


def build_network(rng):
    points = []
    for pid, (x, y) in TRUE_COORDS.items():
        if pid in FIXED_IDS:
            points.append(Point(id=pid, x=x, y=y, fixed=True))
        else:
            points.append(Point(id=pid, x=x + 5.0, y=y - 3.0, fixed=False))

    observations = []
    for i, j in DISTANCE_PAIRS:
        xi, yi = TRUE_COORDS[i]
        xj, yj = TRUE_COORDS[j]
        value = geo.distance(xi, yi, xj, yj) + rng.normal(0.0, SIGMA_DIST)
        observations.append(Observation("distance", i, j, value, SIGMA_DIST))
    for i, j in AZIMUTH_OBS:
        xi, yi = TRUE_COORDS[i]
        xj, yj = TRUE_COORDS[j]
        value = geo.azimuth(xi, yi, xj, yj) + rng.normal(0.0, SIGMA_ANG)
        observations.append(Observation("azimuth", i, j, value, SIGMA_ANG))
    for station, j, k in ANGLE_OBS:
        xi, yi = TRUE_COORDS[station]
        xj, yj = TRUE_COORDS[j]
        xk, yk = TRUE_COORDS[k]
        value = geo.angle(xi, yi, xj, yj, xk, yk) + rng.normal(0.0, SIGMA_ANG)
        observations.append(Observation("angle", station, j, value, SIGMA_ANG, to_id2=k))
    for station, target in DIRECTION_OBS:
        xi, yi = TRUE_COORDS[station]
        xj, yj = TRUE_COORDS[target]
        az = geo.azimuth(xi, yi, xj, yj)
        value = geo.wrap_angle(az - Z_TRUE_D) + rng.normal(0.0, SIGMA_ANG)
        observations.append(Observation("direction", station, target, value, SIGMA_ANG))

    return points, observations


def main():
    rng = np.random.default_rng(123)
    points, observations = build_network(rng)

    print("Approximate coordinates:")
    for p in points:
        tag = "fixed" if p.fixed else "approx"
        print(f"  {p.id}: X={p.x:10.3f}  Y={p.y:10.3f}  ({tag})")

    result = adjust(points, observations)
    accuracies = point_accuracies(result)

    print(f"\nConverged: {result.converged} in {result.iterations} iterations")
    print(f"sigma0 = {result.sigma0:.4f}\n")

    print("Adjusted coordinates and precision:")
    for pid in TRUE_COORDS:
        x, y = result.coords[pid]
        if pid in accuracies:
            acc = accuracies[pid]
            print(
                f"  {pid}: X={x:10.3f}  Y={y:10.3f}  "
                f"sigma_x={acc.sigma_x * 1000:5.1f}mm  sigma_y={acc.sigma_y * 1000:5.1f}mm  "
                f"ellipse a={acc.semi_major * 1000:5.1f}mm b={acc.semi_minor * 1000:5.1f}mm "
                f"theta={math.degrees(acc.orientation):6.1f} deg"
            )
        else:
            print(f"  {pid}: X={x:10.3f}  Y={y:10.3f}  (fixed)")

    if result.orientations:
        orient_acc = orientation_accuracies(result)
        print("\nStation orientation unknowns:")
        for station, z in result.orientations.items():
            sigma_z = orient_acc[station]
            print(
                f"  {station}: Z={math.degrees(z):8.4f} deg  "
                f"(true={math.degrees(Z_TRUE_D):8.4f} deg)  sigma_Z={math.degrees(sigma_z) * 3600:6.2f} arcsec"
            )


if __name__ == "__main__":
    main()
