import os
import tempfile
from pathlib import Path

_test_data = Path(tempfile.mkdtemp(prefix="ufo-platform-tests-"))
os.environ["UFO_DATABASE_PATH"] = str(_test_data / "test.sqlite3")
os.environ["UFO_SESSION_KEY_PATH"] = str(_test_data / "session.key")

from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_public_routes_are_open() -> None:
    assert client.get("/api/sightings").status_code == 200
    assert client.get("/api/export/sightings.csv").status_code == 200
    assert client.get("/static/index.html").status_code == 200
    assert client.get("/console").status_code == 200
    assert client.get("/login").status_code == 404
    assert client.get("/api/health").status_code == 200

def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"

def test_sightings_have_shape() -> None:
    response = client.get("/api/sightings")
    assert response.status_code == 200
    assert response.json()
    assert "shape" in response.json()[0]

def test_sightings_filters_and_analytics() -> None:
    response = client.get("/api/sightings", params={"search": "Phoenix", "mapped": "true"})
    assert response.status_code == 200
    assert response.json()
    assert response.json()[0]["city"] == "Phoenix"

    analytics = client.get("/api/analytics")
    assert analytics.status_code == 200
    assert {"by_month", "by_source", "by_country", "by_shape"} <= analytics.json().keys()

def test_detection_coordinate_update_syncs_sighting() -> None:
    created = client.post(
        "/api/detections",
        json={"confidence": 0.72, "latitude": None, "longitude": None, "notes": "test sync"},
    )
    assert created.status_code == 201
    detection_id = created.json()["id"]
    sighting_id = created.json()["sighting_id"]

    updated = client.patch(
        f"/api/detections/{detection_id}",
        json={"latitude": 13.7563, "longitude": 100.5018},
    )
    assert updated.status_code == 200
    sighting = client.get("/api/sightings", params={"mapped": "true", "search": "test sync"})
    assert any(row["id"] == sighting_id and row["latitude"] == 13.7563 for row in sighting.json())

def test_sightings_csv_export() -> None:
    response = client.get("/api/export/sightings.csv")
    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "id,source,reported_at" in response.text