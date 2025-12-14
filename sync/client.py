
"""
Network synchronization client for SmartLarva Edge.

This module provides a ``SyncClient`` class that encapsulates HTTP
communication with the central server. It handles heartbeat, metadata
upload for events and sensor readings, and binary upload for images.

The API endpoints are assumed to be:

- POST ``/api/heartbeat`` with JSON: ``{ "device_id": ..., "last_event_id": ... }``
  The server responds with a JSON containing at least ``{ "delete_safe_up_to_event_id": ... }``.

- POST ``/api/upload/metadata`` with JSON describing events and sensor readings.
  See the protocol specification for field details.

- PUT ``/api/upload/image/{device_id}/{event_local_id}/{image_index}`` with binary body.
  The request must include a SHA-256 checksum header ``X-Checksum-SHA256`` for verification.

These details may need to be adjusted to match your actual server implementation.
"""

from __future__ import annotations

import logging
from typing import Dict, Any, List, Optional
import requests
import os

class SyncClient:
    """HTTP client for synchronizing edge data with the server."""

    def __init__(self, base_url: str, device_id: str, timeout: int = 10) -> None:
        self.base_url = base_url.rstrip('/')
        self.device_id = device_id
        self.timeout = timeout
        self.session = requests.Session()
        self.logger = logging.getLogger(__name__)

    def send_heartbeat(self, last_event_id: Optional[int]) -> Optional[int]:
        """Send a heartbeat to the server.

        Args:
            last_event_id: Highest local event_id known to be uploaded.

        Returns:
            The safe deletion watermark (delete_safe_up_to_event_id), or None if unavailable.
        """
        url = f'{self.base_url}/api/heartbeat'
        payload: Dict[str, Any] = {
            'device_id': self.device_id,
            'last_event_id': last_event_id,
        }
        try:
            response = self.session.post(url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            data = response.json()
            return data.get('delete_safe_up_to_event_id')
        except Exception as exc:
            self.logger.error('Heartbeat failed: %s', exc)
            return None

    def upload_metadata(self, events_payload: List[Dict[str, Any]]) -> bool:
        """Upload metadata for events and sensor readings.

        Args:
            events_payload: List of event metadata dictionaries.

        Returns:
            True on success, False otherwise.
        """
        url = f'{self.base_url}/api/upload/metadata'
        try:
            response = self.session.post(url, json=events_payload, timeout=self.timeout)
            response.raise_for_status()
            return True
        except Exception as exc:
            self.logger.error('Metadata upload failed: %s', exc)
            return False

    def upload_image(self, event_local_id: int, image_index: int, image_path: str, sha256_hex: str) -> bool:
        """Upload a single image to the server.

        Args:
            event_local_id: local event identifier.
            image_index: index within the burst.
            image_path: path to the image file.
            sha256_hex: precomputed SHA-256 checksum.

        Returns:
            True if upload succeeded, False otherwise.
        """
        url = f'{self.base_url}/api/upload/image/{self.device_id}/{event_local_id}/{image_index}'
        headers = {
            'X-Checksum-SHA256': sha256_hex,
        }
        try:
            with open(image_path, 'rb') as f:
                data = f.read()
            response = self.session.put(url, headers=headers, data=data, timeout=self.timeout)
            response.raise_for_status()
            return True
        except Exception as exc:
            self.logger.error('Image upload failed for %s: %s', image_path, exc)
            return False
