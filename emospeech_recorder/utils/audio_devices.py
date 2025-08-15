"""Utilities for enumerating and labeling audio devices.

Provides helpers to list input/output capable devices using sounddevice
and to format labels for menu display. Kept small and focused so UI code
does not need to depend on sounddevice directly.
"""

from typing import List, Dict, Optional, Tuple

import sounddevice as sd


def list_devices() -> List[Dict]:
    """Return all devices with their attributes from sounddevice.

    Each entry includes index, name, channel caps and defaults.
    """
    devices = sd.query_devices()
    result: List[Dict] = []
    for i, dev in enumerate(devices):
        result.append({
            'index': i,
            'name': dev.get('name', f'Device {i}') or f'Device {i}',
            'max_input_channels': dev.get('max_input_channels', 0),
            'max_output_channels': dev.get('max_output_channels', 0),
            'default_samplerate': dev.get('default_samplerate', None),
            'default_low_input_latency': dev.get('default_low_input_latency', 0.0),
            'default_low_output_latency': dev.get('default_low_output_latency', 0.0),
        })
    return result


def list_input_devices() -> List[Dict]:
    """Return only devices that support input (recording)."""
    return [d for d in list_devices() if (d.get('max_input_channels', 0) or 0) > 0]


def list_output_devices() -> List[Dict]:
    """Return only devices that support output (playback)."""
    return [d for d in list_devices() if (d.get('max_output_channels', 0) or 0) > 0]


def get_device_name_by_index(index: int) -> Optional[str]:
    """Return the device name for a given index, if available."""
    try:
        dev = sd.query_devices(index)
        return dev.get('name')
    except Exception:
        return None


def format_device_label(dev: Dict) -> str:
    """Create a compact label for menus, e.g. "3: Scarlett 2i2 (in=2, out=2)"."""
    idx = dev.get('index', -1)
    name = dev.get('name', f'Device {idx}')
    in_ch = dev.get('max_input_channels', 0) or 0
    out_ch = dev.get('max_output_channels', 0) or 0
    return f"{idx}: {name} (in={in_ch}, out={out_ch})"


def get_default_device_indices() -> Tuple[Optional[int], Optional[int]]:
    """Return current system default (input_idx, output_idx) from sounddevice.

    May return (None, None) if defaults are not available.
    """
    try:
        default = sd.default.device
        if isinstance(default, (list, tuple)) and len(default) == 2:
            in_idx = default[0] if default[0] is not None and default[0] >= 0 else None
            out_idx = default[1] if default[1] is not None and default[1] >= 0 else None
            return in_idx, out_idx
    except Exception:
        pass
    return None, None


def refresh_devices_backend() -> None:
    """Attempt to force-refresh the PortAudio device list.

    Note: sounddevice/PortAudio may cache device lists for the process lifetime.
    These private methods work in practice on most platforms.
    """
    try:
        if hasattr(sd, "_terminate"):
            sd._terminate()  # type: ignore[attr-defined]
        if hasattr(sd, "_initialize"):
            sd._initialize()  # type: ignore[attr-defined]
    except Exception:
        # Best-effort; ignore failures
        pass


def debug_dump_devices() -> None:
    """Print all devices with flags to stdout (for --debug runs)."""
    try:
        devices = list_devices()
        print("\n[DEBUG] Current audio devices:")
        print("=" * 50)
        for d in devices:
            kind = []
            if (d.get('max_input_channels') or 0) > 0:
                kind.append('INPUT')
            if (d.get('max_output_channels') or 0) > 0:
                kind.append('OUTPUT')
            print(f"{d['index']}: {d['name']} [{', '.join(kind)}]")
            print(f"   Channels: in={d.get('max_input_channels',0)}, out={d.get('max_output_channels',0)}")
            if d.get('default_samplerate'):
                print(f"   Default SR: {d['default_samplerate']} Hz")
        print()
    except Exception:
        pass


