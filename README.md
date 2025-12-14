# SmartLarva Edge

SmartLarva Edge is a Python service designed to run on a Raspberry Pi to capture
image bursts and sensor readings, store them locally in SQLite, and synchronize
with a central server. It implements the core features of the SmartLarva
edge–cloud protocol: local identifiers for events and readings, idempotent
metadata uploads, binary image uploads with checksum verification, periodic
heartbeat, and safe cleanup of old data.

## Features

- Modular architecture:
  - Pluggable camera backends (mock for development, libcamera on Raspberry Pi)
  - Pluggable sensors (mock sensor, DHT22 example)
  - Configurable database schema aligned with the protocol
  - HTTP sync client with heartbeat, metadata and image upload
  - Cleanup thread to remove old images safely
- Robust error handling: exceptions are logged and loops continue
- Threaded design: capture, sync, heartbeat and cleanup run concurrently
- YAML-based configuration with sensible defaults
- Logging to file and console

## Directory structure

```
smartlarva_edge/
  __init__.py
  __main__.py
  config.py              # Configuration management
  db.py                  # Database schema and operations
  camera/
    __init__.py
    base.py              # Abstract camera backend
    mock_camera.py       # Mock camera implementation
    rpi_camera.py        # Raspberry Pi camera implementation using libcamera
  sensors/
    __init__.py
    mock_sensors.py      # Mock sensor implementation
    dht22.py             # Example DHT22 sensor implementation
  sync/
    __init__.py
    client.py            # HTTP synchronization client
  main.py                # Main orchestration script
```

## Installation

Clone or download the repository on your development machine. A Python 3.9+
environment is recommended. Install dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -U pip
pip install pyyaml requests pillow adafruit-circuitpython-dht
```

(The Adafruit DHT library is optional; if not installed, the DHT22 sensor backend will
fall back to the mock sensor.)

## Configuration

Create a YAML configuration file, e.g., `config/pi.yaml`:

```yaml
device_id: "your-device-id"
base_url: "https://your-server.example.com"
db_path: "/home/pi/data/smartlarva.db"
image_dir: "/home/pi/data/images"
burst_size: 10
capture_interval: 60
heartbeat_interval: 300
sync_interval: 120
cleanup_interval: 3600
retention_days: 30
camera_backend: "rpi"
sensor_enabled: true
log_file: "/home/pi/data/edge.log"
```

Ensure the directories specified in `db_path`, `image_dir` and `log_file` exist or
allow the service to create them.

## Running

To start the service:

```bash
python -m smartlarva_edge.main --config config/pi.yaml
```

The service will spawn four threads handling capture, heartbeat, sync and cleanup.
Logs are written to both the console and the file specified in `log_file`.

To stop the service, press Ctrl+C or send SIGTERM. The service will cleanly stop
all threads and close the database connection.

## Development and Testing

On a development machine without a physical camera, set `camera_backend` to `mock`
in your configuration. The mock camera generates synthetic images for testing.
Similarly, the mock sensor backend returns random temperature and humidity values.
Use `rsync` or `scp` to deploy the code to your Raspberry Pi when ready.

## Hardware Considerations

The Raspberry Pi backend uses `libcamera` via the `libcamera-still` command-line
tool to capture images. Ensure your Pi has a compatible camera attached and
`libcamera` is installed. Adjust the command parameters in
`smartlarva_edge/camera/rpi_camera.py` as needed for your hardware.

For sensors, the example `DHT22Sensor` uses the Adafruit CircuitPython DHT library.
You may replace or extend this with other sensor types as required.

## Notes

This codebase is intended as a reference implementation. You may need to adapt
endpoints, payloads, and error handling to match your server's API and reliability
requirements. Review the protocol documentation and update the code accordingly.
