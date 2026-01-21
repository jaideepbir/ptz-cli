#!/usr/bin/env python3
import argparse
import json
import os
import subprocess
import sys
import time

import pigpio

PAN_PIN = 13
TILT_PIN = 12

STATE_PATH = os.path.expanduser('~/.cache/ptz_state.json')

DEFAULTS = {
    'pan': 0.0,
    'tilt': 0.0,
    'pan_min': -90.0,
    'pan_max': 90.0,
    'tilt_min': -90.0,
    'tilt_max': 30.0,
}


def now_stamp():
    return time.strftime('%Y%m%d_%H%M%S', time.localtime())


def ensure_pigpiod():
    pi = pigpio.pi()
    if pi.connected:
        return pi
    subprocess.run(['sudo', 'pigpiod'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(0.2)
    pi = pigpio.pi()
    if not pi.connected:
        raise RuntimeError('pigpio daemon not running. Try: sudo pigpiod')
    return pi


def map_angle(angle, in_min=-90.0, in_max=90.0, out_min=250.0, out_max=1250.0):
    return (angle - in_min) * (out_max - out_min) / (in_max - in_min) + out_min


def clamp(val, lo, hi):
    return max(lo, min(hi, val))


def load_state():
    state = DEFAULTS.copy()
    try:
        with open(STATE_PATH, 'r', encoding='utf-8') as f:
            state.update(json.load(f))
    except FileNotFoundError:
        pass
    except Exception:
        pass
    return state


def save_state(state):
    os.makedirs(os.path.dirname(STATE_PATH), exist_ok=True)
    with open(STATE_PATH, 'w', encoding='utf-8') as f:
        json.dump(state, f)


def set_servo(pi, pin, angle):
    pi.set_PWM_frequency(pin, 50)
    pi.set_PWM_range(pin, 10000)
    duty = map_angle(angle)
    pi.set_PWM_dutycycle(pin, duty)


def move_servos(pan, tilt, smooth_ms, state):
    pi = ensure_pigpiod()
    try:
        start_pan = state['pan']
        start_tilt = state['tilt']
        steps = max(1, int(smooth_ms / 20))
        for i in range(1, steps + 1):
            p = start_pan + (pan - start_pan) * i / steps
            t = start_tilt + (tilt - start_tilt) * i / steps
            set_servo(pi, PAN_PIN, p)
            set_servo(pi, TILT_PIN, t)
            time.sleep(0.02)
    finally:
        pi.stop()


def camera_busy_message():
    procs = subprocess.run(
        "ps -ef | egrep 'rpicam|libcamera|vilib|picamera' | grep -v egrep",
        shell=True,
        text=True,
        capture_output=True,
    )
    lines = [
        'Camera appears busy (another process has the device open).',
        'Close any running previews/streams (rpicam-*, libcamera-hello, Vilib).',
    ]
    if procs.stdout.strip():
        lines.append('Active camera-related processes:')
        lines.append(procs.stdout.strip())
    else:
        lines.append('No obvious camera processes found.')
    return "\n".join(lines)


def run_rpicam(args_list):
    proc = subprocess.run(args_list, text=True, capture_output=True)
    if proc.returncode == 0:
        return
    combined = (proc.stdout or '') + (proc.stderr or '')
    if (
        'Pipeline handler in use by another process' in combined
        or 'Device or resource busy' in combined
        or 'failed to acquire camera' in combined
    ):
        print(camera_busy_message(), file=sys.stderr)
    else:
        msg = combined.strip()
        if msg:
            print(msg, file=sys.stderr)
    raise RuntimeError(f"rpicam failed with exit {proc.returncode}")


def cmd_move(args):
    state = load_state()
    pan = state['pan']
    tilt = state['tilt']

    if args.pan is not None:
        pan = args.pan + (pan if args.relative else 0.0)
    if args.tilt is not None:
        tilt = args.tilt + (tilt if args.relative else 0.0)

    pan = clamp(pan, args.pan_min, args.pan_max)
    tilt = clamp(tilt, args.tilt_min, args.tilt_max)

    move_servos(pan, tilt, args.smooth_ms, {'pan': state['pan'], 'tilt': state['tilt']})
    state.update({'pan': pan, 'tilt': tilt, 'pan_min': args.pan_min, 'pan_max': args.pan_max,
                 'tilt_min': args.tilt_min, 'tilt_max': args.tilt_max})
    save_state(state)
    print(f'pan={pan:.1f} tilt={tilt:.1f}')


def cmd_center(_args):
    args = argparse.Namespace(pan=0.0, tilt=0.0, relative=False, smooth_ms=300,
                              pan_min=DEFAULTS['pan_min'], pan_max=DEFAULTS['pan_max'],
                              tilt_min=DEFAULTS['tilt_min'], tilt_max=DEFAULTS['tilt_max'])
    cmd_move(args)


def cmd_status(_args):
    state = load_state()
    print(json.dumps(state, indent=2))


def cmd_photo(args):
    out = args.output
    if not out:
        out = os.path.expanduser(os.path.join('~/Pictures', f'photo_{now_stamp()}.jpg'))
    os.makedirs(os.path.dirname(out), exist_ok=True)

    cmd = ['rpicam-still', '--timeout', str(int(args.timeout_ms)), '--nopreview', '-o', out]
    if args.hflip:
        cmd.append('--hflip')
    if args.vflip:
        cmd.append('--vflip')
    if args.af_mode:
        cmd += ['--autofocus-mode', args.af_mode]
    if args.af_range:
        cmd += ['--autofocus-range', args.af_range]
    if args.af_speed:
        cmd += ['--autofocus-speed', args.af_speed]
    if args.af_on_capture:
        cmd.append('--autofocus-on-capture')
    if args.lens_position is not None:
        cmd += ['--lens-position', str(args.lens_position)]

    run_rpicam(cmd)
    print(out)


def cmd_video(args):
    out = args.output
    if not out:
        out = os.path.expanduser(os.path.join('~/Videos', f'video_{now_stamp()}.h264'))
    os.makedirs(os.path.dirname(out), exist_ok=True)

    timeout_ms = 0 if args.duration_s <= 0 else int(args.duration_s * 1000)
    cmd = ['rpicam-vid', '--timeout', str(timeout_ms), '--nopreview', '-o', out]
    if args.hflip:
        cmd.append('--hflip')
    if args.vflip:
        cmd.append('--vflip')

    run_rpicam(cmd)
    print(out)


def build_parser():
    p = argparse.ArgumentParser(description='PTZ + camera utility for Pi')
    sub = p.add_subparsers(dest='cmd', required=True)

    p_move = sub.add_parser('move', help='Move pan/tilt')
    p_move.add_argument('--pan', type=float, help='Pan angle in degrees')
    p_move.add_argument('--tilt', type=float, help='Tilt angle in degrees')
    p_move.add_argument('--relative', action='store_true', help='Treat pan/tilt as deltas')
    p_move.add_argument('--smooth-ms', type=int, default=300, help='Smooth move duration in ms')
    p_move.add_argument('--pan-min', type=float, default=DEFAULTS['pan_min'])
    p_move.add_argument('--pan-max', type=float, default=DEFAULTS['pan_max'])
    p_move.add_argument('--tilt-min', type=float, default=DEFAULTS['tilt_min'])
    p_move.add_argument('--tilt-max', type=float, default=DEFAULTS['tilt_max'])
    p_move.set_defaults(func=cmd_move)

    p_center = sub.add_parser('center', help='Center pan/tilt')
    p_center.set_defaults(func=cmd_center)

    p_status = sub.add_parser('status', help='Show stored pan/tilt state')
    p_status.set_defaults(func=cmd_status)

    p_photo = sub.add_parser('photo', help='Take a photo')
    p_photo.add_argument('--output', '-o', help='Output file path')
    p_photo.add_argument('--timeout-ms', type=int, default=2000)
    p_photo.add_argument('--hflip', action=argparse.BooleanOptionalAction, default=True)
    p_photo.add_argument('--vflip', action=argparse.BooleanOptionalAction, default=True)
    p_photo.add_argument('--af-mode', choices=['manual', 'auto', 'continuous', 'default'])
    p_photo.add_argument('--af-range', choices=['normal', 'macro', 'full'])
    p_photo.add_argument('--af-speed', choices=['normal', 'fast'])
    p_photo.add_argument('--af-on-capture', action='store_true')
    p_photo.add_argument('--lens-position', type=float)
    p_photo.set_defaults(func=cmd_photo)

    p_video = sub.add_parser('video', help='Record a video')
    p_video.add_argument('--output', '-o', help='Output file path')
    p_video.add_argument('--duration-s', type=float, default=5.0, help='Seconds (0 = until Ctrl+C)')
    p_video.add_argument('--hflip', action=argparse.BooleanOptionalAction, default=True)
    p_video.add_argument('--vflip', action=argparse.BooleanOptionalAction, default=True)
    p_video.set_defaults(func=cmd_video)

    return p


def main():
    parser = build_parser()
    args = parser.parse_args()
    try:
        args.func(args)
    except RuntimeError as e:
        print(f'Error: {e}', file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
