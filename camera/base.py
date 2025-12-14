
"""
Camera backend abstractions for SmartLarva Edge.

This module defines the interface that all camera backends must implement.
A camera backend is responsible for capturing a burst of images, saving them
to disk, computing metadata such as file size and SHA-256 checksum, and
returning a list of ``CapturedImage`` objects.

Implementations may use mock data for development/testing or interact with
real hardware on a Raspberry Pi (e.g., via libcamera or vendor SDK).
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import List
from pathlib import Path
import datetime

@dataclass
class CapturedImage:
    """Represents metadata for a captured image."""

    image_index: int
    local_path: str
    size_bytes: int
    sha256_hex: str
    width_px: int
    height_px: int
    format: str
    captured_at: datetime.datetime

class CameraBackend:
    """Abstract base class for camera backends."""

    def capture_burst(self, event_local_id: int, out_dir: Path, burst_size: int) -> List[CapturedImage]:
        """Capture a burst of images.

        Args:
            event_local_id: The local identifier of the capture event.
            out_dir: Directory where images should be saved. Must exist.
            burst_size: Number of images to capture.

        Returns:
            List of CapturedImage objects.

        Raises:
            NotImplementedError: if not implemented by subclass.
        """
        raise NotImplementedError('capture_burst must be implemented by subclasses')
