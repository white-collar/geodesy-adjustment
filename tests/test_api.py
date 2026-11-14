"""End-to-end tests for the /adjust HTTP endpoint."""

import json
import logging
import math

import pytest
from fastapi.testclient import TestClient

from api.main import app
from geo_adjust.model import Observation, Point
from helpers import TRUE_COORDS, noiseless_observations, perturbed_points

client = TestClient(app)

ANGULAR_TYPES = {"azimuth", "angle", "direction"}


def _reference_points_payload(points: list[Point]) -> list[dict]:
    """Only the fixed points are sent — everything else is inferred from
    the observations and its approximate coordinates computed server-side."""
    return [{"id": p.id, "x": p.x, "y": p.y} for p in points if p.fixed]


def _observations_payload(observations: list[Observation]) -> list[dict]:
    payload = []
    for o in observations:
        if o.type in ANGULAR_TYPES:
            value = math.degrees(o.value)
            sigma = math.degrees(o.sigma) * 3600.0
        else:
            value = o.value
            sigma = o.sigma
        entry = {"type": o.type, "from": o.from_id, "to": o.to_id, "value": value, "sigma": sigma}
        if o.to_id2 is not None:
            entry["to2"] = o.to_id2
        payload.append(entry)
    return payload


def test_adjust_endpoint_matches_core_solver():
    points = perturbed_points()  # only used to pick out the fixed (A, B) rows
    observations = noiseless_observations()

    response = client.post(
        "/adjust",
        json={
            "reference_points": _reference_points_payload(points),
            "observations": _observations_payload(observations),
        },
    )

    assert response.status_code == 200
    data = response.json()
    assert data["converged"] is True
    assert data["rank_deficiency"] == 0

    by_id = {p["id"]: p for p in data["points"]}
    for pid, (true_x, true_y) in TRUE_COORDS.items():
        assert by_id[pid]["x"] == pytest.approx(true_x, abs=1e-6)
        assert by_id[pid]["y"] == pytest.approx(true_y, abs=1e-6)
        if pid not in {"A", "B"}:
            assert by_id[pid]["sigma_x_mm"] is not None
            assert by_id[pid]["error_ellipse"] is not None

    seed_ids = {p["id"] for p in data["seed_points"]}
    assert seed_ids == {"C", "D", "E"}


def test_duplicate_reference_point_returns_400():
    response = client.post(
        "/adjust",
        json={
            "reference_points": [
                {"id": "A", "x": 0.0, "y": 0.0},
                {"id": "A", "x": 1.0, "y": 1.0},
            ],
            "observations": [
                {"type": "distance", "from": "A", "to": "B", "value": 10.0, "sigma": 0.01}
            ],
        },
    )
    assert response.status_code == 400


def test_unresolvable_point_returns_400():
    # X/Y are only tied to each other, with no chain of measurements
    # reaching them from the reference point A.
    response = client.post(
        "/adjust",
        json={
            "reference_points": [{"id": "A", "x": 0.0, "y": 0.0}],
            "observations": [
                {"type": "distance", "from": "X", "to": "Y", "value": 10.0, "sigma": 0.01}
            ],
        },
    )
    assert response.status_code == 400
    assert "X" in response.json()["detail"] or "Y" in response.json()["detail"]


def test_angle_missing_to2_returns_422():
    response = client.post(
        "/adjust",
        json={
            "reference_points": [{"id": "A", "x": 0.0, "y": 0.0}],
            "observations": [
                {"type": "angle", "from": "A", "to": "B", "value": 45.0, "sigma": 1.0}
            ],
        },
    )
    assert response.status_code == 422


def test_free_network_reports_rank_deficiency():
    # No reference points at all: seed.py bootstraps an internal anchor,
    # and the datum (translation) is genuinely underdetermined.
    observations = noiseless_observations()

    response = client.post(
        "/adjust",
        json={"reference_points": [], "observations": _observations_payload(observations)},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["converged"] is True
    assert data["rank_deficiency"] > 0


def _usage_records(caplog):
    return [
        json.loads(r.getMessage().split("usage ", 1)[1])
        for r in caplog.records
        if r.getMessage().startswith("usage ")
    ]


def test_usage_log_on_success_has_counts_and_no_user_data(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    payload = {
        "reference_points": [{"id": "SECRET_ORIGIN", "x": 123456.789, "y": 987654.321}],
        "observations": [
            {"type": "azimuth", "from": "SECRET_ORIGIN", "to": "SECRET_TARGET", "value": 20.0, "sigma": 0.6},
            {"type": "distance", "from": "SECRET_ORIGIN", "to": "SECRET_TARGET", "value": 100.0, "sigma": 0.005},
        ],
    }

    response = client.post("/adjust", json=payload)

    assert response.status_code == 200
    (record,) = _usage_records(caplog)
    assert record["ok"] is True
    assert record["observations"] == 2
    assert record["reference_points"] == 1
    assert record["points"] == 2
    assert record["types"] == {"azimuth": 1, "distance": 1}
    assert record["trace"] is False
    assert record["converged"] is True
    assert "ms" in record
    logged = " ".join(r.getMessage() for r in caplog.records)
    for secret in ("SECRET_ORIGIN", "SECRET_TARGET", "123456", "987654"):
        assert secret not in logged


def test_usage_log_on_error_has_category_and_no_user_data(caplog):
    caplog.set_level(logging.INFO, logger="uvicorn.error")
    payload = {
        "reference_points": [{"id": "SECRET_ORIGIN", "x": 0.0, "y": 0.0}],
        "observations": [
            {"type": "distance", "from": "SECRET_X", "to": "SECRET_Y", "value": 10.0, "sigma": 0.01}
        ],
    }

    response = client.post("/adjust", json=payload)

    assert response.status_code == 400
    (record,) = _usage_records(caplog)
    assert record["ok"] is False
    assert record["error"] == "unresolved_points"
    assert record["observations"] == 1
    logged = " ".join(r.getMessage() for r in caplog.records)
    for secret in ("SECRET_ORIGIN", "SECRET_X", "SECRET_Y"):
        assert secret not in logged
