from __future__ import annotations

import sqlite3
import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = Path(os.environ.get("UFO_DATABASE_PATH", ROOT / "data" / "ufo_platform.sqlite3"))

@contextmanager
def connection() -> Iterator[sqlite3.Connection]:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db() -> None:
    with connection() as conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS sightings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT NOT NULL DEFAULT 'manual', reported_at TEXT,
            city TEXT, state TEXT, country TEXT, shape TEXT, duration TEXT,
            summary TEXT, latitude REAL, longitude REAL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS detections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            detected_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            source TEXT NOT NULL DEFAULT 'camera', confidence REAL NOT NULL,
            image_path TEXT, latitude REAL, longitude REAL, notes TEXT,
            sighting_id INTEGER
        );
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user',
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        );
        """)
        conn.execute("""INSERT OR IGNORE INTO users (username, password_hash, role)
                       SELECT username, password_hash, 'admin' FROM admins""")
        detection_columns = {row[1] for row in conn.execute("PRAGMA table_info(detections)").fetchall()}
        if "sighting_id" not in detection_columns:
            conn.execute("ALTER TABLE detections ADD COLUMN sighting_id INTEGER")
        conn.execute(
            """UPDATE detections
               SET sighting_id = (
                   SELECT id FROM sightings
                   WHERE source = 'camera' AND reported_at = detections.detected_at
                   ORDER BY id DESC LIMIT 1
               )
               WHERE sighting_id IS NULL"""
        )

def seed_demo_data() -> None:
    with connection() as conn:
        if conn.execute("SELECT COUNT(*) FROM sightings").fetchone()[0]:
            return
        conn.executemany("""
        INSERT INTO sightings
        (source, reported_at, city, state, country, shape, duration, summary, latitude, longitude)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            ("NUFORC", "2024-07-14", "Phoenix", "AZ", "US", "triangle", "5 minutes", "Three lights moving silently across the western sky.", 33.4484, -112.0740),
            ("NUFORC", "2023-10-03", "Raleigh", "NC", "US", "disk", "20 seconds", "Bright disc changed direction twice before fading.", 35.7796, -78.6382),
            ("camera", "2026-10-01", "Local camera", "", "", "unknown", "8 seconds", "Camera detection awaiting human review.", None, None),
        ])
