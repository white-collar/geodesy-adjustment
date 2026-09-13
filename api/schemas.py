"""Pydantic request/response models for the /adjust endpoint.

Units at this boundary (not the same as the core solver, which is
radians/meters throughout): distances in meters, angular values in decimal
degrees, angular sigmas in arcseconds. See api/convert.py for the conversion.
"""

from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

ObservationType = Literal["distance", "azimuth", "angle", "direction"]


class ReferencePointIn(BaseModel):
    """A point with precisely known coordinates (опорная точка).

    Every other point id mentioned in `observations` is a point to be
    determined — its approximate coordinates are computed automatically
    (see api/convert.py / geo_adjust/seed.py), not supplied by the caller.
    """

    id: str
    x: float
    y: float


class ObservationIn(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: ObservationType
    from_: str = Field(alias="from")
    to: str
    to2: Optional[str] = None
    value: float
    sigma: float = Field(gt=0)

    @model_validator(mode="after")
    def _check_to2(self) -> "ObservationIn":
        if self.type == "angle" and self.to2 is None:
            raise ValueError("'to2' is required for an angle observation")
        return self


class AdjustRequest(BaseModel):
    reference_points: List[ReferencePointIn]
    observations: List[ObservationIn]
    include_trace: bool = False


class ErrorEllipseOut(BaseModel):
    semi_major_mm: float
    semi_minor_mm: float
    orientation_deg: float


class PointOut(BaseModel):
    id: str
    x: float
    y: float
    fixed: bool
    sigma_x_mm: Optional[float] = None
    sigma_y_mm: Optional[float] = None
    error_ellipse: Optional[ErrorEllipseOut] = None


class OrientationOut(BaseModel):
    station: str
    z_deg: float
    sigma_z_arcsec: float


class ResidualOut(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    type: ObservationType
    from_: str = Field(alias="from")
    to: str
    to2: Optional[str] = None
    value_mm: Optional[float] = None
    value_arcsec: Optional[float] = None


class SeedPointOut(BaseModel):
    id: str
    x: float
    y: float


class AdjustResponse(BaseModel):
    converged: bool
    iterations: int
    sigma0: Optional[float] = None
    rank: int
    rank_deficiency: int
    points: List[PointOut]
    seed_points: List[SeedPointOut]
    orientations: List[OrientationOut]
    residuals: List[ResidualOut]
    trace: List[Dict[str, Any]] = []
