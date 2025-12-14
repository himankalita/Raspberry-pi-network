
"""
Configuration management for SmartLarva Edge.

This module defines a dataclass ``Config`` that holds configuration for the edge
software. It can be loaded from a YAML file or constructed manually. The
configuration covers device identity, API endpoints, paths, capture settings,
intervals for various loops and cleanup, and hardware backend selection.

Example YAML configuration (config/pi.yaml):

```yaml
device_id: "device-001"
base_url: "https://example.com"
db_path: "./edge_data/smartlarva.db"
image_dir: "./edge_data/images"
burst_size: 10
capture_interval: 60        # seconds between bursts
heartbeat_interval: 300     # seconds between heartbeats
sync_interval: 120          # seconds between sync attempts
cleanup_interval: 3600      # seconds between cleanup runs
retention_days: 30
camera_backend: "rpi"       # "mock" on development machines
sensor_enabled: true
log_file: "./edge_data/edge.log"
```

Using the ``Config.from_yaml`` method simplifies loading configuration:

```python
from smartlarva_edge.config import Config
config = Config.from_yaml('config/pi.yaml')
```
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional, Dict, Any
import yaml


@dataclass
class Config:
    """Configuration settings for the SmartLarva Edge software."""

    device_id: str
    base_url: str
    db_path: str = './smartlarva_edge.db'
    image_dir: str = './images'
    burst_size: int = 10
    capture_interval: int = 60  # seconds
    heartbeat_interval: int = 300  # seconds
    sync_interval: int = 120  # seconds
    cleanup_interval: int = 3600  # seconds
    retention_days: int = 30
    camera_backend: str = 'mock'
    sensor_enabled: bool = False
    log_file: str = './edge.log'

    extra: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_yaml(cls, path: str) -> 'Config':
        """Load configuration from a YAML file.

        Raises:
            FileNotFoundError: if the YAML file cannot be found.
            yaml.YAMLError: if the YAML file is invalid.
            KeyError: if required keys are missing.
        """
        with open(path, 'r') as f:
            data = yaml.safe_load(f)

        # Basic validation of required keys
        required_keys = ['device_id', 'base_url']
        missing = [k for k in required_keys if k not in data]
        if missing:
            raise KeyError(f'Missing required configuration keys: {missing}')

        return cls(
            device_id=data['device_id'],
            base_url=data['base_url'],
            db_path=data.get('db_path', './smartlarva_edge.db'),
            image_dir=data.get('image_dir', './images'),
            burst_size=data.get('burst_size', 10),
            capture_interval=data.get('capture_interval', 60),
            heartbeat_interval=data.get('heartbeat_interval', 300),
            sync_interval=data.get('sync_interval', 120),
            cleanup_interval=data.get('cleanup_interval', 3600),
            retention_days=data.get('retention_days', 30),
            camera_backend=data.get('camera_backend', 'mock'),
            sensor_enabled=bool(data.get('sensor_enabled', False)),
            log_file=data.get('log_file', './edge.log'),
            extra={k: v for k, v in data.items() if k not in cls.__annotations__},
        )

    def ensure_paths(self) -> None:
        """Ensure that filesystem paths exist for DB and image storage.

        Creates directories as needed. This method is idempotent.
        """
        # Create directory for DB file if necessary
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        if not os.path.exists(self.image_dir):
            os.makedirs(self.image_dir, exist_ok=True)

        # Create directory for log file
        log_dir = os.path.dirname(self.log_file)
        if log_dir and not os.path.exists(log_dir):
            os.makedirs(log_dir, exist_ok=True)
