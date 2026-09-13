"""Parametric least-squares adjustment of a 2D geodetic network.

Handles both well-constrained (fixed) and free/weakly-constrained networks:
the normal-equation solve falls back to a symmetric pseudo-inverse when the
fixed points and observations don't fully determine the datum (translation,
rotation and/or scale), giving the minimum-norm solution.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

import numpy as np
from scipy.linalg import pinvh

from . import geometry as geo
from .model import Observation, Point


@dataclass
class AdjustmentResult:
    coords: Dict[str, Tuple[float, float]]
    orientations: Dict[str, float]
    iterations: int
    converged: bool
    residuals: np.ndarray
    sigma0: float
    Qx: np.ndarray
    point_unknown_order: List[str]
    orientation_unknown_order: List[str]
    rank: int
    N: np.ndarray = field(repr=False)


def _index_point_unknowns(points: List[Point]) -> Dict[str, int]:
    index = {}
    i = 0
    for p in points:
        if not p.fixed:
            index[p.id] = i
            i += 2
    return index


def _index_orientation_unknowns(observations: List[Observation], base: int) -> Dict[str, int]:
    index: Dict[str, int] = {}
    for obs in observations:
        if obs.type == "direction" and obs.from_id not in index:
            index[obs.from_id] = base + len(index)
    return index


def _initial_orientations(
    coords: Dict[str, Tuple[float, float]],
    observations: List[Observation],
    orientation_index: Dict[str, int],
) -> Dict[str, float]:
    sums: Dict[str, List[float]] = {station: [] for station in orientation_index}
    for obs in observations:
        if obs.type == "direction" and obs.from_id in orientation_index:
            xi, yi = coords[obs.from_id]
            xj, yj = coords[obs.to_id]
            calc_az = geo.azimuth(xi, yi, xj, yj)
            sums[obs.from_id].append(geo.wrap_angle(calc_az - obs.value))
    return {station: sum(vals) / len(vals) for station, vals in sums.items()}


def _pseudo_solve(N: np.ndarray, rhs: np.ndarray, rcond: float):
    """Solve N x = rhs via a symmetric pseudo-inverse. Returns (x, rank(N)).

    A rank-deficient N (free/weakly-constrained network) is usually only
    *numerically* near-singular, not exactly singular, so a Cholesky
    factorization with an exception-based fallback is not reliable here: it
    can silently "succeed" on a near-null direction and return a wildly
    ill-conditioned wrong answer instead of raising. Thresholding the
    eigenvalues via `rcond` (as pinvh does) catches that case correctly,
    giving the minimum-norm solution when the datum is underdetermined and
    the exact solution when it is not.
    """
    inv, rank = pinvh(N, rtol=rcond, return_rank=True)
    return inv @ rhs, rank


def _build_system(
    coords: Dict[str, Tuple[float, float]],
    orientations: Dict[str, float],
    observations: List[Observation],
    point_index: Dict[str, int],
    orientation_index: Dict[str, int],
    n_unknowns: int,
):
    n_obs = len(observations)
    A = np.zeros((n_obs, n_unknowns))
    l = np.zeros(n_obs)
    weights = np.zeros(n_obs)

    def add_point(row: int, point_id: str, dvx: float, dvy: float) -> None:
        if point_id in point_index:
            j = point_index[point_id]
            A[row, j] += dvx
            A[row, j + 1] += dvy

    for row, obs in enumerate(observations):
        xi, yi = coords[obs.from_id]
        xj, yj = coords[obs.to_id]
        weights[row] = 1.0 / (obs.sigma**2)

        if obs.type == "distance":
            calc = geo.distance(xi, yi, xj, yj)
            dxi, dyi, dxj, dyj = geo.distance_partials(xi, yi, xj, yj)
            add_point(row, obs.from_id, dxi, dyi)
            add_point(row, obs.to_id, dxj, dyj)
            l[row] = obs.value - calc

        elif obs.type == "azimuth":
            calc = geo.azimuth(xi, yi, xj, yj)
            dxi, dyi, dxj, dyj = geo.azimuth_partials(xi, yi, xj, yj)
            add_point(row, obs.from_id, dxi, dyi)
            add_point(row, obs.to_id, dxj, dyj)
            l[row] = geo.wrap_angle(obs.value - calc)

        elif obs.type == "angle":
            xk, yk = coords[obs.to_id2]
            calc = geo.angle(xi, yi, xj, yj, xk, yk)
            dxi, dyi, dxj, dyj, dxk, dyk = geo.angle_partials(xi, yi, xj, yj, xk, yk)
            add_point(row, obs.from_id, dxi, dyi)
            add_point(row, obs.to_id, dxj, dyj)
            add_point(row, obs.to_id2, dxk, dyk)
            l[row] = geo.wrap_angle(obs.value - calc)

        elif obs.type == "direction":
            z = orientations[obs.from_id]
            calc = geo.wrap_angle(geo.azimuth(xi, yi, xj, yj) - z)
            dxi, dyi, dxj, dyj = geo.azimuth_partials(xi, yi, xj, yj)
            add_point(row, obs.from_id, dxi, dyi)
            add_point(row, obs.to_id, dxj, dyj)
            A[row, orientation_index[obs.from_id]] = -1.0
            l[row] = geo.wrap_angle(obs.value - calc)

        else:
            raise ValueError(f"unknown observation type: {obs.type}")

    return A, l, weights


def adjust(
    points: List[Point],
    observations: List[Observation],
    max_iter: int = 10,
    tol: float = 1e-8,
    rcond: float = 1e-10,
) -> AdjustmentResult:
    coords = {p.id: (p.x, p.y) for p in points}
    point_index = _index_point_unknowns(points)
    point_order = sorted(point_index, key=lambda pid: point_index[pid])
    n_point_unknowns = 2 * len(point_index)

    orientation_index = _index_orientation_unknowns(observations, base=n_point_unknowns)
    orientation_order = sorted(orientation_index, key=lambda s: orientation_index[s])
    n_unknowns = n_point_unknowns + len(orientation_index)

    if n_unknowns == 0:
        raise ValueError("network has no free points or orientations to adjust")

    orientations = _initial_orientations(coords, observations, orientation_index)

    A = l = weights = N = None
    delta = np.zeros(n_unknowns)
    rank = 0
    converged = False
    iterations = 0

    for iterations in range(1, max_iter + 1):
        A, l, weights = _build_system(
            coords, orientations, observations, point_index, orientation_index, n_unknowns
        )
        Aw = A * weights[:, None]
        N = Aw.T @ A
        b = Aw.T @ l

        delta, rank = _pseudo_solve(N, b, rcond)

        for pid, j in point_index.items():
            x, y = coords[pid]
            coords[pid] = (x + delta[j], y + delta[j + 1])
        for station, j in orientation_index.items():
            orientations[station] = geo.wrap_angle(orientations[station] + delta[j])

        if np.max(np.abs(delta)) < tol:
            converged = True
            break

    residuals = A @ delta - l
    dof = len(observations) - rank
    if dof > 0:
        sigma0_sq = float(residuals @ (weights * residuals)) / dof
        sigma0 = sigma0_sq**0.5
    else:
        sigma0 = float("nan")

    Qx, rank = _pseudo_solve(N, np.eye(n_unknowns), rcond)

    return AdjustmentResult(
        coords=coords,
        orientations=orientations,
        iterations=iterations,
        converged=converged,
        residuals=residuals,
        sigma0=sigma0,
        Qx=Qx,
        point_unknown_order=point_order,
        orientation_unknown_order=orientation_order,
        rank=rank,
        N=N,
    )
