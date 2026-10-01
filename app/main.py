from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from .database import connection, init_db, seed_demo_data

ROOT = Path(__file__).resolve().parents[1]
app = FastAPI(title="UFO Intelligence Platform", version="0.1.0")
app.mount("/static", StaticFiles(directory=ROOT / "static"), name="static")
init_db()
seed_demo_data()

class DetectionCreate(BaseModel):
    confidence: float = Field(ge=0, le=1)
    image_path: str | None = None
    latitude: float | None = None
    longitude: float | None = None
    notes: str = ""


class DetectionUpdate(BaseModel):
    confidence: float | None = Field(default=None, ge=0, le=1)
    latitude: float | None = None
    longitude: float | None = None
    notes: str | None = None



@app.get("/", include_in_schema=False)
def landing():
    return FileResponse(ROOT / "index.html")


@app.get("/console", include_in_schema=False)
def dashboard():
    return FileResponse(ROOT / "static" / "index.html")


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "ufo-platform"}

@app.get("/api/sightings")
def list_sightings(
    limit: int = 100,
    source: str | None = None,
    search: str | None = None,
    shape: str | None = None,
    country: str | None = None,
    mapped: bool | None = None,
) -> list[dict]:
    limit = max(1, min(limit, 500))
    query = "SELECT * FROM sightings WHERE 1=1"
    params: list[str | int | float] = []
    if source:
        query += " AND source = ?"
        params.append(source)
    if search:
        query += " AND (city LIKE ? OR state LIKE ? OR country LIKE ? OR summary LIKE ? OR shape LIKE ?)"
        term = f"%{search}%"
        params.extend([term] * 5)
    if shape:
        query += " AND shape = ?"
        params.append(shape)
    if country:
        query += " AND country = ?"
        params.append(country)
    if mapped is True:
        query += " AND latitude IS NOT NULL AND longitude IS NOT NULL"
    elif mapped is False:
        query += " AND (latitude IS NULL OR longitude IS NULL)"
    query += " ORDER BY reported_at DESC, id DESC LIMIT ?"
    params.append(limit)
    with connection() as conn:
        rows = conn.execute(query, params).fetchall()
    return [dict(row) for row in rows]

@app.get("/api/stats")
def stats() -> dict:
    with connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]
        detections = conn.execute("SELECT COUNT(*) FROM detections").fetchone()[0]
        camera_sightings = conn.execute("SELECT COUNT(*) FROM sightings WHERE source = 'camera'").fetchone()[0]
        shapes = conn.execute(
            "SELECT COALESCE(shape, 'unknown') AS shape, COUNT(*) AS count FROM sightings GROUP BY shape ORDER BY count DESC"
        ).fetchall()
    return {"total_sightings": total, "camera_detections": detections, "camera_sightings": camera_sightings, "top_shapes": [dict(row) for row in shapes]}


@app.get("/api/analytics")
def analytics() -> dict:
    with connection() as conn:
        by_month = conn.execute(
            """SELECT substr(reported_at, 1, 7) AS month, COUNT(*) AS count
               FROM sightings WHERE reported_at IS NOT NULL GROUP BY month ORDER BY month"""
        ).fetchall()
        by_source = conn.execute(
            "SELECT COALESCE(source, 'unknown') AS source, COUNT(*) AS count FROM sightings GROUP BY source ORDER BY count DESC"
        ).fetchall()
        by_country = conn.execute(
            "SELECT COALESCE(NULLIF(country, ''), 'Unknown') AS country, COUNT(*) AS count FROM sightings GROUP BY country ORDER BY count DESC LIMIT 10"
        ).fetchall()
        by_shape = conn.execute(
            "SELECT COALESCE(NULLIF(shape, ''), 'unknown') AS shape, COUNT(*) AS count FROM sightings GROUP BY shape ORDER BY count DESC LIMIT 10"
        ).fetchall()
    return {
        "by_month": [dict(row) for row in by_month],
        "by_source": [dict(row) for row in by_source],
        "by_country": [dict(row) for row in by_country],
        "by_shape": [dict(row) for row in by_shape],
    }


@app.get("/api/detections")
def list_detections(limit: int = 100) -> list[dict]:
    limit = max(1, min(limit, 500))
    with connection() as conn:
        rows = conn.execute("SELECT * FROM detections ORDER BY detected_at DESC, id DESC LIMIT ?", (limit,)).fetchall()
    return [dict(row) for row in rows]


@app.patch("/api/detections/{detection_id}")
def update_detection(detection_id: int, payload: DetectionUpdate) -> dict:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update.")
    assignments = ", ".join(f"{key} = ?" for key in updates)
    with connection() as conn:
        existing = conn.execute("SELECT sighting_id FROM detections WHERE id = ?", (detection_id,)).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Detection not found.")
        cursor = conn.execute(f"UPDATE detections SET {assignments} WHERE id = ?", (*updates.values(), detection_id))
        sighting_id = existing["sighting_id"]
        if sighting_id and ("latitude" in updates or "longitude" in updates):
            coordinates = conn.execute(
                "SELECT latitude, longitude FROM detections WHERE id = ?", (detection_id,)
            ).fetchone()
            conn.execute(
                "UPDATE sightings SET latitude = ?, longitude = ? WHERE id = ?",
                (coordinates["latitude"], coordinates["longitude"], sighting_id),
            )
        row = conn.execute("SELECT * FROM detections WHERE id = ?", (detection_id,)).fetchone()
    return dict(row)


@app.get("/api/export/sightings.csv")
def export_sightings() -> StreamingResponse:
    with connection() as conn:
        rows = conn.execute("SELECT * FROM sightings ORDER BY reported_at DESC, id DESC").fetchall()
    output = io.StringIO()
    writer = csv.writer(output)
    columns = rows[0].keys() if rows else ["id", "source", "reported_at", "city", "state", "country", "shape", "duration", "summary", "latitude", "longitude", "created_at"]
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row[column] for column in columns])
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=ufo-sightings.csv"},
    )

@app.post("/api/detections", status_code=201)
def create_detection(payload: DetectionCreate) -> dict:
    detected_at = datetime.now(timezone.utc).isoformat()
    with connection() as conn:
        sighting = conn.execute(
            """INSERT INTO sightings
               (source, reported_at, city, shape, summary, latitude, longitude)
               VALUES ('camera', ?, 'Local camera', 'unknown', ?, ?, ?)""",
            (detected_at, payload.notes or "Camera detection awaiting human review.", payload.latitude, payload.longitude),
        )
        sighting_id = sighting.lastrowid
        cursor = conn.execute(
            """INSERT INTO detections
               (detected_at, confidence, image_path, latitude, longitude, notes, sighting_id)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (detected_at, payload.confidence, payload.image_path, payload.latitude, payload.longitude, payload.notes, sighting_id),
        )
    return {"id": cursor.lastrowid, "sighting_id": sighting_id, "detected_at": detected_at, **payload.model_dump()}

@app.post("/api/import/nuforc")
async def import_nuforc(file: UploadFile = File(...)) -> dict[str, int]:
    if not file.filename or not file.filename.lower().endswith((".csv", ".txt")):
        raise HTTPException(status_code=400, detail="Upload a CSV or TXT export.")
    content = await file.read()
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig", errors="replace")))
    imported = 0
    with connection() as conn:
        for row in reader:
            conn.execute(
                """
                INSERT INTO sightings (source, reported_at, city, state, country, shape, duration, summary, latitude, longitude)
                VALUES ('NUFORC', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (row.get("datetime") or row.get("date") or row.get("reported_at"), row.get("city"), row.get("state"), row.get("country"), row.get("shape"), row.get("duration") or row.get("duration (hours/min)"), row.get("comments") or row.get("summary") or row.get("description"), _number(row.get("latitude")), _number(row.get("longitude"))),
            )
            imported += 1
    return {"imported": imported}

def _number(value: str | None) -> float | None:
    try:
        return float(value) if value else None
    except ValueError:
        return None
