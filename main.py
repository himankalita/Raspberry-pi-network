
"""
Main orchestration for SmartLarva Edge.

This script coordinates camera capture, sensor reading, heartbeat communication,
metadata upload, image upload, and cleanup operations. It runs multiple
background threads to perform each task periodically. The core components
are configurable via a YAML configuration file (see :mod:`smartlarva_edge.config`).

Usage:

```bash
python -m smartlarva_edge.main --config config/pi.yaml
```
"""

from __future__ import annotations

import argparse
import datetime
import logging
import signal
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Any

import os  # Needed for file operations in cleanup loop

from .config import Config
from .db import Database, CapturedImageRecord, CaptureEventRecord, SensorReadingRecord, CrateRecord
from .camera.base import CameraBackend
from .camera.mock_camera import MockCamera
from .camera.rpi_camera import RpiCamera
from .sensors.mock_sensors import MockSensor
# Note: DHT22 sensor is imported lazily inside _init_sensor to avoid
# import errors on platforms without the library.
from .sync.client import SyncClient


class SmartLarvaEdge:
    """Main controller for SmartLarva Edge operations."""

    def __init__(self, config: Config) -> None:
        self.config = config
        # Ensure directories exist
        config.ensure_paths()

        # Initialize logging
        self._setup_logging()

        self.db = Database(config.db_path)
        # Resolve the crate once at startup. This will create the crate row if it
        # does not exist and store its ID for reuse in all events. If the
        # configuration does not provide a ``crate`` section, a default crate
        # will be created using the label 'default_crate'.
        self.crate_id = self._ensure_crate()
        # Initialize hardware backends
        self.camera: CameraBackend = self._init_camera()
        self.sensor = self._init_sensor()
        self.sync_client = SyncClient(base_url=config.base_url, device_id=config.device_id)
        # Generate counters for local IDs
        self._event_counter = self._get_max_id('capture_events_local', 'event_id')
        self._reading_counter = self._get_max_id('sensor_readings_local', 'reading_id')

        self._stop_event = threading.Event()
        self._threads: list[threading.Thread] = []

    def _setup_logging(self) -> None:
        """Configure logging to file and console."""
        logger = logging.getLogger()
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter(
            '%(asctime)s [%(levelname)s] %(threadName)s - %(message)s'
        )
        # File handler
        fh = logging.FileHandler(self.config.log_file)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
        # Console handler
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    def _init_camera(self) -> CameraBackend:
        """Instantiate the camera backend based on configuration."""
        if self.config.camera_backend == 'mock':
            return MockCamera()
        elif self.config.camera_backend == 'rpi':
            return RpiCamera()
        else:
            raise ValueError(f'Unknown camera backend: {self.config.camera_backend}')

    def _init_sensor(self):
        """Instantiate a sensor backend if enabled.

        Sensor selection can be configured via the ``sensor_backend`` field
        in the configuration. If ``sensor_enabled`` is false, this method
        returns ``None``. The supported backends are:

          - ``mock``: generate random temperature/humidity values (works on any platform)
          - ``dht22``: use a DHT22 sensor via the Adafruit_DHT or CircuitPython
            library. The GPIO pin can be specified via ``dht22_pin`` in
            ``config.extra``. Lazy import is used so that missing libraries
            do not cause top-level import errors on development machines.
        """
        if not self.config.sensor_enabled:
            return None
        # Determine backend from config.extra or fallback to mock
        backend = None
        # Try sensor_backend attribute first (if added to Config), then extra
        backend = getattr(self.config, 'sensor_backend', None)
        if not backend:
            backend = self.config.extra.get('sensor_backend', 'mock')
        backend = backend.lower()
        if backend == 'mock':
            return MockSensor()
        if backend == 'dht22':
            # Lazy import to avoid missing Adafruit_DHT on non-Pi systems
            try:
                from .sensors.dht22 import DHT22Sensor  # type: ignore
            except Exception:
                # Fallback to mock if the real sensor library is unavailable
                return MockSensor()
            # Determine GPIO pin from config
            pin = self.config.extra.get('dht22_pin', 4)
            return DHT22Sensor(pin=pin)
        # Unknown backend -> fallback to mock
        return MockSensor()

    def _ensure_crate(self) -> int:
        """Ensure a crate exists and return its ID.

        This method reads crate metadata from the configuration (``config.extra``).
        The expected YAML structure is::

            crate:
              label: "crate_01"
              location: "BioLab A"
              notes: "High protein feed"
              started_at: "2025-02-01"
              ended_at: null

        If no crate configuration is provided, a default crate with label
        ``'default_crate'`` is created. The crate metadata is inserted into
        ``crates_local`` if it does not already exist, and the resulting
        ``id`` is returned.
        """
        # Validate crate configuration exists and is a dict
        if not self.config.extra or not isinstance(self.config.extra.get('crate'), dict):
            raise ValueError('Missing `crate:` section in YAML (config.extra).')

        crate_cfg = self.config.extra['crate']

        # Require id, label, and started_at fields
        if 'id' not in crate_cfg:
            raise ValueError('Missing `crate.id` in YAML. ID must be provided.')
        if 'label' not in crate_cfg:
            raise ValueError('Missing `crate.label` in YAML.')
        if 'started_at' not in crate_cfg:
            raise ValueError('Missing `crate.started_at` in YAML.')

        crate_id = int(crate_cfg['id'])
        label = crate_cfg['label']
        location = crate_cfg.get('location')
        notes = crate_cfg.get('notes')
        started_at = crate_cfg['started_at']
        ended_at = crate_cfg.get('ended_at')

        # Insert or retrieve crate id
        return self.db.insert_crate(
            CrateRecord(
                id=crate_id,
                crate_label=label,
                location=location,
                notes=notes,
                created_at=started_at,
                ended_at=ended_at,
            )
        )

    def _get_max_id(self, table: str, column: str) -> int:
        """Get the current maximum ID from a table/column."""
        row = self.db.conn.execute(
            f'SELECT MAX({column}) as max_id FROM {table}'
        ).fetchone()
        max_id = row['max_id']
        return max_id if max_id is not None else 0

    # Loop implementations

    def capture_loop(self) -> None:
        """Periodically capture images and sensor readings."""
        while not self._stop_event.is_set():
            try:
                # Determine new event ID
                self._event_counter += 1
                event_id = self._event_counter
                # Use the pre-resolved crate id
                crate_id = self.crate_id
                # Timestamp for the event
                captured_at = datetime.datetime.utcnow().isoformat()
                # Capture sensor reading if sensor available
                if self.sensor:
                    self._reading_counter += 1
                    reading_id = self._reading_counter
                    reading = self.sensor.read(crate_id=crate_id, reading_id=reading_id)
                    # Insert into DB
                    self.db.insert_sensor_reading(SensorReadingRecord(
                        reading_id=reading.reading_id,
                        crate_id=reading.crate_id,
                        recorded_at=reading.recorded_at.isoformat(),
                        temperature_c=reading.temperature_c,
                        humidity_pct=reading.humidity_pct,
                        uploaded=0,
                    ))
                # Capture images
                out_dir = Path(self.config.image_dir)
                images = self.camera.capture_burst(event_local_id=event_id, out_dir=out_dir, burst_size=self.config.burst_size)
                # Determine camera name from config.extra or use default
                camera_name = self.config.extra.get('camera_name', 'camera_0')
                # Insert capture event metadata
                self.db.insert_event(CaptureEventRecord(
                    event_id=event_id,
                    crate_id=crate_id,
                    camera_name=camera_name,
                    captured_at=captured_at,
                    burst_size=len(images),
                    uploaded=0,
                ))
                # Insert images into DB
                for img in images:
                    self.db.insert_image(CapturedImageRecord(
                        id=None,
                        event_local_id=event_id,
                        image_index=img.image_index,
                        local_path=img.local_path,
                        captured_at=img.captured_at.isoformat(),
                        size_bytes=img.size_bytes,
                        sha256_hex=img.sha256_hex,
                        width_px=img.width_px,
                        height_px=img.height_px,
                        format=img.format,
                        metadata_uploaded=0,
                        uploaded=0,
                        local_exists=1,
                        corrupted=0,
                    ))
                logging.info(f'Captured event {event_id} with {len(images)} images')
            except Exception as exc:
                logging.exception('Capture loop error: %s', exc)
            # Sleep until next capture
            self._stop_event.wait(self.config.capture_interval)

    def heartbeat_loop(self) -> None:
        """Periodically send heartbeat to server and update safe delete watermark."""
        while not self._stop_event.is_set():
            try:
                last_event_id = self._get_max_id('capture_events_local', 'event_id')
                safe_id = self.sync_client.send_heartbeat(last_event_id=last_event_id)
                if safe_id is not None:
                    self.db.set_state_value('delete_safe_up_to_event_id', str(safe_id))
                    logging.info(f'Heartbeat successful; safe delete up to event_id {safe_id}')
            except Exception as exc:
                logging.exception('Heartbeat loop error: %s', exc)
            self._stop_event.wait(self.config.heartbeat_interval)

    def sync_loop(self) -> None:
        """Periodically upload metadata and images to the server."""
        while not self._stop_event.is_set():
            try:
                # Upload metadata for events
                events = self.db.get_unsynced_events(limit=5)
                if events:
                    payload = []
                    for event in events:
                        images = self.db.get_images_for_event(event['event_id'])
                        event_meta: Dict[str, Any] = {
                            'device_id': self.config.device_id,
                            'event_local_id': event['event_id'],
                            'crate_id': event['crate_id'],
                            'camera_name': event['camera_name'],
                            'captured_at': event['captured_at'],
                            'burst_size': event['burst_size'],
                            'images': [
                                {
                                    'image_index': img['image_index'],
                                    'size_bytes': img['size_bytes'],
                                    'sha256_hex': img['sha256_hex'],
                                    'width_px': img['width_px'],
                                    'height_px': img['height_px'],
                                    'format': img['format'],
                                } for img in images
                            ],
                        }
                        payload.append(event_meta)
                    if self.sync_client.upload_metadata(events_payload=payload):
                        for event in events:
                            self.db.mark_event_uploaded(event['event_id'])
                            self.db.mark_image_metadata_uploaded(event['event_id'])
                        logging.info(f'Uploaded metadata for {len(events)} events')
                # Upload sensor readings metadata separately
                readings = self.db.get_sensor_readings(uploaded=0, limit=10)
                if readings:
                    sensor_payload = [{
                        'device_id': self.config.device_id,
                        'reading_local_id': r['reading_id'],
                        'crate_id': r['crate_id'],
                        'recorded_at': r['recorded_at'],
                        'temperature_c': r['temperature_c'],
                        'humidity_pct': r['humidity_pct'],
                    } for r in readings]
                    if self.sync_client.upload_metadata(events_payload=sensor_payload):
                        for r in readings:
                            self.db.mark_reading_uploaded(r['reading_id'])
                        logging.info(f'Uploaded {len(readings)} sensor readings')
                # Upload image binaries
                images = self.db.get_unsynced_images(limit=3)
                for img in images:
                    success = self.sync_client.upload_image(
                        event_local_id=img['event_local_id'],
                        image_index=img['image_index'],
                        image_path=img['local_path'],
                        sha256_hex=img['sha256_hex'],
                    )
                    if success:
                        self.db.mark_image_uploaded(img['event_local_id'], img['image_index'])
                        logging.info(f'Uploaded image {img["local_path"]}')
                    else:
                        # Mark as corrupted to avoid infinite retries
                        self.db.mark_image_corrupted(img['id'])
            except Exception as exc:
                logging.exception('Sync loop error: %s', exc)
            self._stop_event.wait(self.config.sync_interval)

    def cleanup_loop(self) -> None:
        """Periodically delete local image files that are safe to remove."""
        while not self._stop_event.is_set():
            try:
                safe_id_str = self.db.get_state_value('delete_safe_up_to_event_id')
                if safe_id_str is not None:
                    safe_id = int(safe_id_str)
                    candidates = self.db.get_cleanup_candidates(
                        safe_delete_event_id=safe_id,
                        retention_days=self.config.retention_days,
                        limit=20
                    )
                    for img in candidates:
                        path = img['local_path']
                        try:
                            if os.path.exists(path):
                                os.remove(path)
                            self.db.mark_image_deleted(img['id'])
                            logging.info(f'Cleaned up image {path}')
                        except Exception as exc:
                            logging.error(f'Failed to delete {path}: {exc}')
                else:
                    logging.debug('No safe delete watermark yet')
            except Exception as exc:
                logging.exception('Cleanup loop error: %s', exc)
            self._stop_event.wait(self.config.cleanup_interval)

    def start(self) -> None:
        """Start all background threads."""
        loops = [
            ('CaptureLoop', self.capture_loop),
            ('HeartbeatLoop', self.heartbeat_loop),
            ('SyncLoop', self.sync_loop),
            ('CleanupLoop', self.cleanup_loop),
        ]
        for name, target in loops:
            t = threading.Thread(name=name, target=target)
            t.daemon = True
            t.start()
            self._threads.append(t)

    def stop(self) -> None:
        """Signal threads to stop and wait for completion."""
        self._stop_event.set()
        for t in self._threads:
            t.join(timeout=5.0)
        self.db.close()

def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='SmartLarva Edge Service')
    parser.add_argument('--config', '-c', type=str, required=True, help='Path to YAML configuration file')
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    config = Config.from_yaml(args.config)
    service = SmartLarvaEdge(config)

    def handle_sigterm(signum, frame):
        logging.info('Shutting down...')
        service.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, handle_sigterm)
    signal.signal(signal.SIGTERM, handle_sigterm)
    service.start()
    # Keep the main thread alive
    while True:
        time.sleep(1)

if __name__ == '__main__':
    main()
