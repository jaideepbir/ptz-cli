# PTZ CLI

Small CLI utility to control the pan/tilt servos and capture photos/videos using `rpicam-*` on a Raspberry Pi.

## Usage

```
./ptz_cli.py move --pan -30 --tilt 0 --smooth-ms 400
./ptz_cli.py move --pan -10 --relative
./ptz_cli.py center
./ptz_cli.py status

./ptz_cli.py photo
./ptz_cli.py photo --af-mode auto --af-on-capture

./ptz_cli.py video --duration-s 10
```

## Dependencies

- `pigpio` daemon (`sudo pigpiod`)
- Python package: `pigpio`
- `rpicam-still`, `rpicam-vid` (from `rpicam-apps`)

## Notes

- Stores last pan/tilt in `~/.cache/ptz_state.json`.
- Uses BCM pins 13 (pan) and 12 (tilt).
- Default limits: pan -90..90, tilt -90..30.
