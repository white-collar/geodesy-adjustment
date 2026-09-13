"""FastAPI wrapper around the geo_adjust solver.

Run with: uvicorn api.main:app --reload
"""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles

from geo_adjust.solver import adjust

from .convert import build_observations, build_points, build_response, validate_references
from .schemas import AdjustRequest, AdjustResponse

app = FastAPI(title="Geodetic Network Adjustment API")
WEB_DIR = Path(__file__).resolve().parent.parent / "web"


@app.post("/adjust", response_model=AdjustResponse)
def adjust_network(request: AdjustRequest) -> AdjustResponse:
    try:
        validate_references(request)
        observations = build_observations(request)
        points, seed_coords = build_points(request, observations)
        result = adjust(points, observations)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return build_response(request, request.observations, result, seed_coords)


# Mounted last: API routes above take precedence, static files fill everything else.
app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
