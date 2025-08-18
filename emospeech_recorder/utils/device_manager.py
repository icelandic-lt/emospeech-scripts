"""Centralized audio device management.

This module provides a DeviceManager class that handles all device-related
operations including enumeration, capability checking, and name-to-index mapping.
"""

from typing import List, Dict, Optional, Tuple
import sounddevice as sd


class DeviceManager:
    """Manages audio device operations and mappings."""

    def __init__(self):
        """Initialize the device manager."""
        self._refresh_cache()

    def _refresh_cache(self):
        """Refresh the internal device cache."""
        self._devices = sd.query_devices()
        self._all_devices = []
        self._input_devices = []
        self._output_devices = []

        for i, dev in enumerate(self._devices):
            device_info = {
                "index": i,
                "name": dev.get("name", f"Device {i}"),
                "max_input_channels": dev.get("max_input_channels", 0),
                "max_output_channels": dev.get("max_output_channels", 0),
                "default_samplerate": dev.get("default_samplerate"),
                "default_low_input_latency": dev.get("default_low_input_latency", 0.0),
                "default_low_output_latency": dev.get(
                    "default_low_output_latency", 0.0
                ),
                "hostapi": dev.get("hostapi"),
            }
            self._all_devices.append(device_info)

            if dev.get("max_input_channels", 0) > 0:
                self._input_devices.append(device_info)

            if dev.get("max_output_channels", 0) > 0:
                self._output_devices.append(device_info)

    def refresh(self):
        """Force refresh of device list."""
        # Try to refresh PortAudio backend
        try:
            if hasattr(sd, "_terminate"):
                sd._terminate()
            if hasattr(sd, "_initialize"):
                sd._initialize()
        except:
            pass
        self._refresh_cache()

    def get_all_devices(self) -> List[Dict]:
        """Get list of all devices.

        Returns:
            List of device info dictionaries
        """
        return self._all_devices.copy()

    def get_input_devices(self) -> List[Dict]:
        """Get list of all input devices.

        Returns:
            List of device info dictionaries
        """
        return self._input_devices.copy()

    def get_output_devices(self) -> List[Dict]:
        """Get list of all output devices.

        Returns:
            List of device info dictionaries
        """
        return self._output_devices.copy()

    def get_device_by_name(self, name: str) -> Optional[Dict]:
        """Get device info by name.

        Args:
            name: Device name to search for

        Returns:
            Device info dict or None if not found
        """
        for dev in self._input_devices:
            if dev["name"] == name:
                return dev.copy()
        return None

    def get_device_index_by_name(self, name: str) -> Optional[int]:
        """Get device index by name.

        Args:
            name: Device name to search for

        Returns:
            Device index or None if not found
        """
        device = self.get_device_by_name(name)
        return device["index"] if device else None

    def get_device_name_by_index(self, index: int) -> Optional[str]:
        """Get device name by index.

        Args:
            index: Device index

        Returns:
            Device name or None if not found
        """
        for dev in self._all_devices:
            if dev["index"] == index:
                return dev["name"]
        return None

    @staticmethod
    def get_default_input_device() -> Optional[int]:
        """Get the system's default input device index.

        Returns:
            Default input device index or None
        """
        try:
            default = sd.default.device
            if isinstance(default, (list, tuple)) and len(default) == 2:
                in_idx = default[0]
                if in_idx is not None and in_idx >= 0:
                    return in_idx
        except:
            pass
        return None

    @staticmethod
    def get_default_device_indices() -> Tuple[Optional[int], Optional[int]]:
        """Get system default (input_idx, output_idx) from sounddevice.

        Returns:
            Tuple of (input_index, output_index), may contain None values
        """
        try:
            default = sd.default.device
            if isinstance(default, (list, tuple)) and len(default) == 2:
                in_idx = (
                    default[0] if default[0] is not None and default[0] >= 0 else None
                )
                out_idx = (
                    default[1] if default[1] is not None and default[1] >= 0 else None
                )
                return in_idx, out_idx
        except Exception:
            pass
        return None, None

    def get_supported_sample_rates(
        self, device_name: Optional[str] = None
    ) -> List[int]:
        """Get supported sample rates for a device.

        Args:
            device_name: Device name (None for system default)

        Returns:
            List of supported sample rates
        """
        device_index = None
        if device_name:
            device_index = self.get_device_index_by_name(device_name)
            if device_index is None:
                # Fallback
                return [48000]
        else:
            device_index = self.get_default_input_device()

        # Common sample rates to test
        standard_rates = [
            8000,
            11025,
            16000,
            22050,
            24000,
            32000,
            44100,
            48000,
            88200,
            96000,
            176400,
            192000,
        ]

        if device_index is None:
            # Return common rates for system default
            return [16000, 22050, 44100, 48000]

        supported_rates = []

        try:
            device_info = self._devices[device_index]
            # Add device's default rate if available
            default_rate = device_info.get("default_samplerate")
            if default_rate and default_rate > 0:
                default_rate = int(default_rate)
                if default_rate not in standard_rates:
                    standard_rates.append(default_rate)
                    standard_rates.sort()

            # Test each rate
            for rate in standard_rates:
                try:
                    sd.check_input_settings(
                        device=device_index,
                        channels=1,
                        dtype="float32",
                        samplerate=rate,
                    )
                    supported_rates.append(rate)
                except:
                    pass

        except Exception:
            # Fallback to common rates
            supported_rates = [16000, 22050, 44100, 48000]

        return supported_rates if supported_rates else [48000]

    def get_supported_bit_depths(
        self, device_name: Optional[str], sample_rate: int
    ) -> List[int]:
        """Get supported bit depths for a device at a specific sample rate.

        Args:
            device_name: Device name (None for system default)
            sample_rate: Sample rate to test at

        Returns:
            List of supported bit depths (16, 24)
        """
        device_index = None
        if device_name:
            device_index = self.get_device_index_by_name(device_name)
            if device_index is None:
                return [16, 24]  # Fallback
        else:
            device_index = self.get_default_input_device()

        if device_index is None:
            # Return both for system default
            return [16, 24]

        supported_depths = []

        try:
            # Test 16-bit
            try:
                sd.check_input_settings(
                    device=device_index,
                    channels=1,
                    dtype="int16",
                    samplerate=sample_rate,
                )
                supported_depths.append(16)
            except:
                pass

            # Test 24-bit (using int32)
            try:
                sd.check_input_settings(
                    device=device_index,
                    channels=1,
                    dtype="int32",
                    samplerate=sample_rate,
                )
                supported_depths.append(24)
            except:
                pass

        except Exception:
            # Default to both
            supported_depths = [16, 24]

        return supported_depths if supported_depths else [16, 24]

    def check_device_compatibility(
        self,
        device_name: Optional[str],
        sample_rate: int,
        bit_depth: int,
        channels: int = 1,
    ) -> bool:
        """Check if a device supports the given audio configuration.

        Args:
            device_name: Device name (None or "default" for system default)
            sample_rate: Sample rate in Hz
            bit_depth: Bit depth (16 or 24)
            channels: Number of channels

        Returns:
            True if configuration is supported
        """

        device_index = None
        if device_name and device_name != "default":
            device_index = self.get_device_index_by_name(device_name)
            if device_index is None:
                return False
        else:
            device_index = self.get_default_input_device()

        # Check channel support (only if we have a specific device)
        if device_index is not None:
            device_info = self._devices[device_index]
            max_channels = device_info.get("max_input_channels", 0)
            if max_channels < channels:
                return False

        # Map bit depth to dtype
        dtype_map = {16: "int16", 24: "int32"}
        if bit_depth not in dtype_map:
            return False

        # Test the configuration
        try:
            sd.check_input_settings(
                device=device_index,  # None is valid for system default
                channels=channels,
                dtype=dtype_map[bit_depth],
                samplerate=sample_rate,
            )
            return True
        except Exception:
            return False

    def find_compatible_device(
        self,
        sample_rate: int,
        bit_depth: int,
        channels: int = 1,
        preferred_name: Optional[str] = None,
    ) -> Optional[str]:
        """Find a compatible device for the given configuration.

        Args:
            sample_rate: Required sample rate
            bit_depth: Required bit depth
            channels: Required channels
            preferred_name: Try this device first

        Returns:
            Name of compatible device, "default" for system default, or None if no device found
        """
        # Try preferred device first (if not "default")
        if preferred_name and preferred_name != "default":
            if self.check_device_compatibility(
                preferred_name, sample_rate, bit_depth, channels
            ):
                return preferred_name

        # Try system default
        if self.check_device_compatibility(None, sample_rate, bit_depth, channels):
            return "default"  # Return "default" string for system default

        # Try all devices
        for dev in self._input_devices:
            if self.check_device_compatibility(
                dev["name"], sample_rate, bit_depth, channels
            ):
                return dev["name"]

        return None  # No compatible device found

    def format_device_label(self, device: Dict) -> str:
        """Create a compact label for menus.

        Args:
            device: Device info dictionary

        Returns:
            Formatted label like "3: Scarlett 2i2 (in=2, out=2)"
        """
        idx = device.get("index", -1)
        name = device.get("name", f"Device {idx}")
        in_ch = device.get("max_input_channels", 0) or 0
        out_ch = device.get("max_output_channels", 0) or 0
        return f"{idx}: {name} (in={in_ch}, out={out_ch})"

    def format_device_label_by_name(self, device_name: Optional[str]) -> str:
        """Format a device name for display.

        Args:
            device_name: Device name or None for system default

        Returns:
            Formatted label for display
        """
        if device_name is None:
            return "System Default"

        device = self.get_device_by_name(device_name)
        if device:
            channels = device.get("max_input_channels", 0)
            return f"{device_name} (Ch: {channels})"

        return device_name

    def debug_dump_devices(self) -> None:
        """Print all devices with flags to stdout (for debug runs)."""
        try:
            devices = self.get_all_devices()
            print("\n[DEBUG] Current audio devices:")
            print("=" * 50)
            for d in devices:
                kind = []
                if (d.get("max_input_channels") or 0) > 0:
                    kind.append("INPUT")
                if (d.get("max_output_channels") or 0) > 0:
                    kind.append("OUTPUT")
                print(f"{d['index']}: {d['name']} [{', '.join(kind)}]")
                print(
                    f"   Channels: in={d.get('max_input_channels',0)}, out={d.get('max_output_channels',0)}"
                )
                if d.get("default_samplerate"):
                    print(f"   Default SR: {d['default_samplerate']} Hz")
            print()
        except Exception:
            pass


# Global instance for convenience
_device_manager = None


def get_device_manager() -> DeviceManager:
    """Get the global DeviceManager instance.

    Returns:
        The global DeviceManager instance
    """
    global _device_manager
    if _device_manager is None:
        _device_manager = DeviceManager()
    return _device_manager
