
"""
Raspberry Pi camera backend.

This backend uses the libcamera tools available on Raspberry Pi OS to capture
bursts of images. It invokes ``libcamera-still`` or ``libcamera-raw`` via
subprocess, saving images to disk in rapid succession.

Note: To use this backend, ensure that libcamera is installed and the camera
is enabled on your Raspberry Pi. This code is designed as an example and
may need adjustments depending on your specific hardware and performance
requirements.

If libcamera is not available (e.g., when running on macOS), this module will
raise ``NotImplementedError`` when ``capture_burst`` is called.
"""

from __future__ import annotations

import datetime
import os
import subprocess
from pathlib import Path
from typing import List

from .base import CameraBackend, CapturedImage


class RpiCamera(CameraBackend):
    """Camera backend using libcamera tools on Raspberry Pi."""

    def __init__(self, image_width: int = 4056, image_height: int = 3040, quality: int = 90) -> None:
        self.image_width = image_width
        self.image_height = image_height
        self.quality = quality

    def _compute_sha256(self, path: str) -> str:
        import hashlib
        h = hashlib.sha256()
        with open(path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        return h.hexdigest()

    def capture_burst(self, event_local_id: int, out_dir: Path, burst_size: int) -> List[CapturedImage]:
        """Capture a burst using libcamera-still.

        Args:
            event_local_id: Local ID for the capture event.
            out_dir: Directory to save images.
            burst_size: Number of images.

        Returns:
            List of ``CapturedImage`` objects.

        Raises:
            RuntimeError: if capturing fails.
        """
        # Build output filename pattern
        pattern = str(out_dir / f'{event_local_id:08d}_%03d.jpg')
        cmd = [
            'libcamera-still',
            '-n',                        # no preview
            '-o', pattern,
            '--width', str(self.image_width),
            '--height', str(self.image_height),
            '--quality', str(self.quality),
            '--timelapse', '100',
            '--frames', str(burst_size),
        ]
        # Ensure output directory exists
        os.makedirs(out_dir, exist_ok=True)
        try:
            result = subprocess.run(cmd, check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        except FileNotFoundError:
            raise NotImplementedError('libcamera-still is not available on this system')
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f'libcamera-still failed: {exc.stderr.decode().strip()}')

        captured: List[CapturedImage] = []
        # libcamera-still names files starting at 000.jpg
        for idx in range(burst_size):
            filename = f'{event_local_id:08d}_{idx:03d}.jpg'
            path = out_dir / filename
            if not path.exists():
                continue
            size_bytes = os.path.getsize(path)
            sha256_hex = self._compute_sha256(str(path))
            # We don't attempt to read image dimensions here; width/height could be None
            captured.append(CapturedImage(
                image_index=idx,
                local_path=str(path),
                size_bytes=size_bytes,
                sha256_hex=sha256_hex,
                width_px=self.image_width,
                height_px=self.image_height,
                format='jpg',
                captured_at=datetime.datetime.utcnow(),
            ))
        return captured
