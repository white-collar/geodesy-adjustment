"""Precision estimates derived from an AdjustmentResult."""

import math
from dataclasses import dataclass
from typing import Dict

import numpy as np

from .solver import AdjustmentResult


@dataclass
class PointAccuracy:
    sigma_x: float
    sigma_y: float
    semi_major: float
    semi_minor: float
    orientation: float  # radians, clockwise from X axis, direction of semi-major axis


def point_accuracies(result: AdjustmentResult) -> Dict[str, PointAccuracy]:
    """Standard deviations and error ellipse per free point.

    Qx blocks are scaled by sigma0^2 to get the covariance matrix Cx.
    If sigma0 is NaN (zero redundancy), sigma0 is treated as 1.0 so that
    relative precision (Qx itself) is still reported.
    """
    scale = result.sigma0 if result.sigma0 == result.sigma0 else 1.0
    out = {}
    for idx, pid in enumerate(result.point_unknown_order):
        j = idx * 2
        block = result.Qx[j : j + 2, j : j + 2] * (scale**2)
        sigma_x = math.sqrt(block[0, 0])
        sigma_y = math.sqrt(block[1, 1])

        eigvals, eigvecs = np.linalg.eigh(block)
        # eigh returns ascending order; largest last
        semi_minor, semi_major = math.sqrt(max(eigvals[0], 0.0)), math.sqrt(max(eigvals[1], 0.0))
        major_vec = eigvecs[:, 1]
        orientation = math.atan2(major_vec[1], major_vec[0])

        out[pid] = PointAccuracy(
            sigma_x=sigma_x,
            sigma_y=sigma_y,
            semi_major=semi_major,
            semi_minor=semi_minor,
            orientation=orientation,
        )
    return out


def orientation_accuracies(result: AdjustmentResult) -> Dict[str, float]:
    """Standard deviation (radians) of each station's estimated orientation unknown."""
    scale = result.sigma0 if result.sigma0 == result.sigma0 else 1.0
    n_points = len(result.point_unknown_order) * 2
    out = {}
    for idx, station in enumerate(result.orientation_unknown_order):
        j = n_points + idx
        out[station] = math.sqrt(result.Qx[j, j]) * scale
    return out
