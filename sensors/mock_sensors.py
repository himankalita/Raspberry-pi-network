
"""
Mock sensors for development and testing.

This module defines a simple temperature and humidity sensor that returns
random values. It can be used on development machines to simulate a real
sensor such as DHT22 or BME280.
"""

from __future__ import annotations
import random
import datetime
from typing import Optional
from dataclasses import dataclass

@dataclass
class SensorReading:
    """Represents a sensor reading."""
    reading_id: int
    crate_id: int
    recorded_at: datetime.datetime
    temperature_c: Optional[float]
    humidity_pct: Optional[float]

class MockSensor:
    """Mock sensor returning random temperature and humidity."""

    def read(self, crate_id: int, reading_id: int) -> SensorReading:
        """Return a simulated sensor reading for a crate.

        Args:
            crate_id: Identifier of the crate being monitored.
            reading_id: Local identifier for the reading.

        Returns:
            A SensorReading dataclass instance.
        """
        now = datetime.datetime.utcnow()
        temperature = round(random.uniform(18.0, 25.0), 2)
        humidity = round(random.uniform(40.0, 70.0), 2)
        return SensorReading(
            reading_id=reading_id,
            crate_id=crate_id,
            recorded_at=now,
            temperature_c=temperature,
            humidity_pct=humidity,
        )
