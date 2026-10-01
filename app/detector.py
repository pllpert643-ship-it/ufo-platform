from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

@dataclass
class Detection:
    confidence: float
    image_path: str | None = None
    notes: str = ""

class UFODetector:
    """Adapter boundary for the upstream camera detector."""
    def __init__(self, model_path: str | None = None) -> None:
        self.model_path = Path(model_path) if model_path else None

    def detect(self, frame: Any) -> Detection | None:
        # Replace with the upstream detector's inference call.
        return None

def detect_image(path: str) -> Detection | None:
    return UFODetector().detect(path)
