"""FastAPI wrapper around the geo_adjust solver.

Run with: uvicorn api.main:app --reload
"""

import json
import logging
import time
from collections import Counter
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from geo_adjust.solver import adjust

from .convert import build_observations, build_points, build_response, validate_references
from .schemas import AdjustRequest, AdjustResponse

app = FastAPI(title="Geodetic Network Adjustment API")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"

# Reuses uvicorn's logger so the line is emitted at INFO without extra setup.
usage_log = logging.getLogger("uvicorn.error")


def _log_usage(**fields) -> None:
    """One greppable line per calculation: `usage {"ok":true,...}`.

    Only counts and flags are logged. Users enter survey coordinates, which
    can be sensitive, so point ids, coordinates, measurement values and error
    messages (which quote point ids) must never end up here.
    """
    usage_log.info("usage %s", json.dumps(fields, separators=(",", ":")))


def _error_category(message: str) -> str:
    if "duplicate reference point" in message:
        return "duplicate_reference_point"
    if "could not compute approximate coordinates" in message:
        return "unresolved_points"
    return "invalid_input"


@app.post("/adjust", response_model=AdjustResponse)
def adjust_network(request: AdjustRequest) -> AdjustResponse:
    started = time.perf_counter()
    summary = {
        "reference_points": len(request.reference_points),
        "observations": len(request.observations),
        "types": dict(Counter(o.type for o in request.observations)),
        "trace": request.include_trace,
    }

    try:
        validate_references(request)
        observations = build_observations(request)
        points, seed_coords = build_points(request, observations)
        result = adjust(points, observations, trace=request.include_trace)
    except ValueError as exc:
        _log_usage(
            ok=False,
            error=_error_category(str(exc)),
            ms=round((time.perf_counter() - started) * 1000),
            **summary,
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    response = build_response(request, request.observations, result, seed_coords)
    _log_usage(
        ok=True,
        points=len(response.points),
        converged=response.converged,
        iterations=response.iterations,
        rank_deficiency=response.rank_deficiency,
        ms=round((time.perf_counter() - started) * 1000),
        **summary,
    )
    return response


# Mounted last: API routes above take precedence, static files fill everything else.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
