"""Unit conversions and mapping between the API schema and geo_adjust core objects."""

import math
from typing import Dict, List, Tuple

from geo_adjust.accuracy import orientation_accuracies, point_accuracies
from geo_adjust.model import Observation, Point
from geo_adjust.seed import compute_initial_coordinates
from geo_adjust.solver import AdjustmentResult

from .schemas import (
    AdjustRequest,
    AdjustResponse,
    ErrorEllipseOut,
    ObservationIn,
    OrientationOut,
    PointOut,
    ResidualOut,
    SeedPointOut,
)

ANGULAR_TYPES = {"azimuth", "angle", "direction"}


def deg_to_rad(deg: float) -> float:
    return math.radians(deg)


def rad_to_deg(rad: float) -> float:
    return math.degrees(rad)


def arcsec_to_rad(arcsec: float) -> float:
    return math.radians(arcsec / 3600.0)


def rad_to_arcsec(rad: float) -> float:
    return math.degrees(rad) * 3600.0


def m_to_mm(meters: float) -> float:
    return meters * 1000.0


def validate_references(request: AdjustRequest) -> None:
    """Boundary validation the core library doesn't do (and shouldn't): catch
    duplicate reference-point ids before they cause silently-wrong results.
    Any id appearing only in observations is a point to be determined —
    there is no "unknown point" to reject at this stage anymore."""
    ids = [p.id for p in request.reference_points]
    duplicates = {pid for pid in ids if ids.count(pid) > 1}
    if duplicates:
        raise ValueError(f"duplicate reference point id(s): {sorted(duplicates)}")


def build_observations(request: AdjustRequest) -> List[Observation]:
    observations = []
    for obs in request.observations:
        if obs.type in ANGULAR_TYPES:
            value = deg_to_rad(obs.value)
            sigma = arcsec_to_rad(obs.sigma)
        else:
            value = obs.value
            sigma = obs.sigma
        observations.append(
            Observation(
                type=obs.type,
                from_id=obs.from_,
                to_id=obs.to,
                value=value,
                sigma=sigma,
                to_id2=obs.to2,
            )
        )
    return observations


def build_points(
    request: AdjustRequest, observations: List[Observation]
) -> Tuple[List[Point], Dict[str, Tuple[float, float]]]:
    """Reference points keep their given (exact) coordinates; every other
    point id mentioned in `observations` gets its approximate coordinates
    computed automatically. Returns (points_for_adjust, seed_coords) where
    seed_coords covers only the non-reference points (for reporting)."""
    fixed_ids = {p.id for p in request.reference_points}
    fixed_points = [Point(id=p.id, x=p.x, y=p.y, fixed=True) for p in request.reference_points]

    coords, unresolved = compute_initial_coordinates(fixed_points, observations)
    if unresolved:
        raise ValueError(
            "could not compute approximate coordinates for point(s): "
            f"{unresolved} — no chain of measurements from a reference point reaches "
            "them (pure intersection/resection is not supported yet)"
        )

    points = [
        Point(id=pid, x=x, y=y, fixed=(pid in fixed_ids)) for pid, (x, y) in coords.items()
    ]
    seed_coords = {pid: xy for pid, xy in coords.items() if pid not in fixed_ids}
    return points, seed_coords


def _residual_out(obs_in: ObservationIn, residual: float) -> ResidualOut:
    kwargs = dict(type=obs_in.type, from_=obs_in.from_, to=obs_in.to, to2=obs_in.to2)
    if obs_in.type in ANGULAR_TYPES:
        kwargs["value_arcsec"] = rad_to_arcsec(residual)
    else:
        kwargs["value_mm"] = m_to_mm(residual)
    return ResidualOut(**kwargs)


def build_response(
    request: AdjustRequest,
    observations_in: List[ObservationIn],
    result: AdjustmentResult,
    seed_coords: Dict[str, Tuple[float, float]],
) -> AdjustResponse:
    accuracies = point_accuracies(result)
    orient_acc = orientation_accuracies(result)
    fixed_ids = {p.id for p in request.reference_points}

    points_out = []
    for pid, (x, y) in result.coords.items():
        acc = accuracies.get(pid)
        error_ellipse = None
        sigma_x_mm = sigma_y_mm = None
        if acc is not None:
            sigma_x_mm = m_to_mm(acc.sigma_x)
            sigma_y_mm = m_to_mm(acc.sigma_y)
            error_ellipse = ErrorEllipseOut(
                semi_major_mm=m_to_mm(acc.semi_major),
                semi_minor_mm=m_to_mm(acc.semi_minor),
                orientation_deg=rad_to_deg(acc.orientation),
            )
        points_out.append(
            PointOut(
                id=pid,
                x=x,
                y=y,
                fixed=(pid in fixed_ids),
                sigma_x_mm=sigma_x_mm,
                sigma_y_mm=sigma_y_mm,
                error_ellipse=error_ellipse,
            )
        )

    seed_points_out = [SeedPointOut(id=pid, x=x, y=y) for pid, (x, y) in seed_coords.items()]

    orientations_out = [
        OrientationOut(
            station=station,
            z_deg=rad_to_deg(result.orientations[station]),
            sigma_z_arcsec=rad_to_arcsec(orient_acc[station]),
        )
        for station in result.orientation_unknown_order
    ]

    residuals_out = [
        _residual_out(obs_in, residual)
        for obs_in, residual in zip(observations_in, result.residuals)
    ]

    n_unknowns = 2 * len(result.point_unknown_order) + len(result.orientation_unknown_order)
    sigma0 = result.sigma0 if result.sigma0 == result.sigma0 else None  # NaN check

    return AdjustResponse(
        converged=result.converged,
        iterations=result.iterations,
        sigma0=sigma0,
        rank=result.rank,
        rank_deficiency=n_unknowns - result.rank,
        points=points_out,
        seed_points=seed_points_out,
        orientations=orientations_out,
        residuals=residuals_out,
    )
