
"""
DHT22 sensor backend using Adafruit_DHT.

This module provides an example implementation for reading data from a
DHT22 or similar temperature/humidity sensor. It uses the Adafruit_DHT
library, which must be installed on the Raspberry Pi (e.g., via pip).
If the library or sensor is not available, the ``read`` method will raise
a RuntimeError.
"""

from __future__ import annotations
import datetime
from typing import Optional
from dataclasses import dataclass

import Adafruit_DHT

@dataclass
class SensorReading:
    reading_id: int
    crate_id: int
    recorded_at: datetime.datetime
    temperature_c: Optional[float]
    humidity_pct: Optional[float]

class DHT22Sensor:
    """DHT22 sensor backend."""

    def __init__(self, pin: int) -> None:
        self.sensor = Adafruit_DHT.DHT22
        self.pin = pin

    def read(self, crate_id: int, reading_id: int) -> SensorReading:
        """Read temperature and humidity from the sensor.

        Args:
            crate_id: crate identifier.
            reading_id: local reading identifier.

        Returns:
            SensorReading object with temperature and humidity values.

        Raises:
            RuntimeError: if reading fails or sensor returns None values.
        """
        humidity, temperature = Adafruit_DHT.read_retry(self.sensor, self.pin)
        if humidity is None or temperature is None:
            raise RuntimeError('Failed to read from DHT22 sensor')
        return SensorReading(
            reading_id=reading_id,
            crate_id=crate_id,
            recorded_at=datetime.datetime.utcnow(),
            temperature_c=temperature,
            humidity_pct=humidity,
        )
