"""Data model for a 2D geodetic network.

Coordinate convention: X = north (abscissa), Y = east (ordinate), matching the
classic Russian/Ukrainian geodesy convention (Bolshakov/Gan'shin). Directional
angles and observed angles are in radians, measured clockwise from the X axis.
"""

from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class Point:
    id: str
    x: float
    y: float
    fixed: bool = False


@dataclass
class Observation:
    """A single observation.

    - distance: from_id -> to_id, value in the same linear units as coordinates.
    - azimuth: from_id -> to_id, value in radians, already oriented (e.g. gyro/GNSS).
    - angle: horizontal angle at from_id, turned from to_id (first ray) to
      to_id2 (second ray), value in radians. Orientation-free: does not
      require an unknown instrument-zero correction.
    - direction: circle reading at from_id (station) toward to_id (target),
      value in radians. Unlike azimuth, this is relative to an arbitrary
      instrument zero, so the solver introduces one unknown orientation
      correction per station that has direction observations.
    """

    type: Literal["distance", "azimuth", "angle", "direction"]
    from_id: str
    to_id: str
    value: float
    sigma: float
    to_id2: Optional[str] = None

    def __post_init__(self) -> None:
        if self.type == "angle" and self.to_id2 is None:
            raise ValueError("angle observation requires to_id2")
        if self.sigma <= 0:
            raise ValueError("sigma must be positive")
