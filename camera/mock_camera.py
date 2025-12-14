
"""
Mock camera backend for development and testing on machines without a physical camera.

This implementation creates synthetic images using the Pillow library. Each
image is filled with a solid color and optionally annotated with the event ID
and index. The images are saved to the specified directory and metadata
computed (file size, SHA-256).

Usage:

```python
from smartlarva_edge.camera.mock_camera import MockCamera
cam = MockCamera(image_width=640, image_height=480)
images = cam.capture_burst(event_local_id=1, out_dir=Path('./images'), burst_size=5)
```
"""

from __future__ import annotations

import datetime
import hashlib
import os
from pathlib import Path
from typing import List
import random

from PIL import Image, ImageDraw, ImageFont

from .base import CameraBackend, CapturedImage


class MockCamera(CameraBackend):
    """Mock camera backend that generates synthetic images."""

    def __init__(self, image_width: int = 640, image_height: int = 480) -> None:
        self.image_width = image_width
        self.image_height = image_height
        # Try to load a default font for annotation; fallback gracefully.
        try:
            self.font = ImageFont.load_default()
        except Exception:
            self.font = None

    def _save_image(self, img: Image.Image, path: str) -> None:
        """Save image to disk."""
        img.save(path, format='JPEG', quality=90)

    def _compute_sha256(self, path: str) -> str:
        """Compute SHA-256 checksum of a file."""
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()

    def capture_burst(self, event_local_id: int, out_dir: Path, burst_size: int) -> List[CapturedImage]:
        """Generate a burst of synthetic images.

        Each image is a solid color chosen randomly. The image filename
        encodes the event and index for easy identification.

        Args:
            event_local_id: Local ID of the capture event.
            out_dir: Directory to save images.
            burst_size: Number of images to generate.

        Returns:
            List of CapturedImage instances.
        """
        captured: List[CapturedImage] = []
        now = datetime.datetime.utcnow()
        for idx in range(burst_size):
            # Create a random solid color image
            r, g, b = [random.randint(0, 255) for _ in range(3)]
            img = Image.new('RGB', (self.image_width, self.image_height), color=(r, g, b))

            # Optionally draw text annotation on the image
            if self.font:
                draw = ImageDraw.Draw(img)
                text = f"Event {event_local_id}\nIdx {idx}"
                try:
                    draw.text((10, 10), text, fill=(255 - r, 255 - g, 255 - b), font=self.font)
                except Exception:
                    pass

            filename = f'{event_local_id:08d}_{idx:03d}.jpg'
            path = out_dir / filename
            # Ensure the output directory exists
            os.makedirs(out_dir, exist_ok=True)
            self._save_image(img, str(path))
            size_bytes = os.path.getsize(path)
            sha256_hex = self._compute_sha256(str(path))
            width_px, height_px = img.size
            captured.append(CapturedImage(
                image_index=idx,
                local_path=str(path),
                size_bytes=size_bytes,
                sha256_hex=sha256_hex,
                width_px=width_px,
                height_px=height_px,
                format='jpg',
                captured_at=now,
            ))
        return captured
