"""Audio devices submenu builder for Settings → Device.

Creates a compact 'Device' submenu with:
- Rescan (refresh devices list)
- Input Device (radio list of input-capable devices)
- Output Device (radio list of output-capable devices)

This module keeps Tk menu logic separate from the main window to avoid
growing existing files further.
"""

from typing import Callable, Optional
import tkinter as tk

from ...utils.device_manager import get_device_manager


class AudioDevicesMenuBuilder:
    """Builds and manages the Settings → Device submenu."""

    def __init__(
        self,
        parent_settings_menu: tk.Menu,
        *,
        on_select_input: Optional[Callable[[int], None]] = None,
        on_select_output: Optional[Callable[[int], None]] = None,
        on_select_input_channels: Optional[Callable[[Optional[list]], None]] = None,
        on_select_output_channels: Optional[Callable[[Optional[list]], None]] = None,
        initial_input_index: Optional[int] = None,
        initial_output_index: Optional[int] = None,
        initial_input_mapping: Optional[list] = None,
        initial_output_mapping: Optional[list] = None,
        debug: bool = False,
    ) -> None:
        self.parent_settings_menu = parent_settings_menu
        self.on_select_input = on_select_input
        self.on_select_output = on_select_output
        self.on_select_input_channels = on_select_input_channels
        self.on_select_output_channels = on_select_output_channels
        self.debug = debug
        # Store initial mappings for first build
        self._initial_input_mapping = initial_input_mapping
        self._initial_output_mapping = initial_output_mapping

        # Main "Device" submenu
        self.device_menu = tk.Menu(self.parent_settings_menu, tearoff=0)
        self.parent_settings_menu.add_cascade(label="Device", menu=self.device_menu)

        # Variables to track current selection
        # If no initial indices provided, try system defaults for initial check state
        if initial_input_index is None or initial_output_index is None:
            device_manager = get_device_manager()
            def_in, def_out = device_manager.get_default_device_indices()
            if initial_input_index is None:
                initial_input_index = def_in if def_in is not None else -1
            if initial_output_index is None:
                initial_output_index = def_out if def_out is not None else -1

        self.input_var = tk.IntVar(
            value=-1 if initial_input_index is None else initial_input_index
        )
        self.output_var = tk.IntVar(
            value=-1 if initial_output_index is None else initial_output_index
        )

        # Submenus
        self.input_menu = tk.Menu(self.device_menu, tearoff=0)
        self.output_menu = tk.Menu(self.device_menu, tearoff=0)
        self.input_channels_menu = tk.Menu(self.device_menu, tearoff=0)
        self.output_channels_menu = tk.Menu(self.device_menu, tearoff=0)

        # Channel selection state variables
        self.input_channels_var = tk.StringVar()
        self.output_channels_var = tk.StringVar()
        # Default selection
        self.input_channels_var.set(
            "default" if not self._initial_input_mapping else "custom"
        )
        self.output_channels_var.set(
            "default" if not self._initial_output_mapping else "custom"
        )

        # Build initial menu
        self._build_menu()

    def _build_menu(self) -> None:
        # Clear existing
        self.device_menu.delete(0, tk.END)

        # Rescan command
        self.device_menu.add_command(label="Rescan Devices", command=self._on_rescan)
        self.device_menu.add_separator()

        # Input devices submenu
        self.input_menu = tk.Menu(self.device_menu, tearoff=0)
        self.device_menu.add_cascade(label="Input Device", menu=self.input_menu)
        self._populate_input_devices()

        # Input channels submenu
        self.device_menu.add_cascade(
            label="Input Channels", menu=self.input_channels_menu
        )
        self._populate_input_channels(self._initial_input_mapping)

        # Output devices submenu
        self.output_menu = tk.Menu(self.device_menu, tearoff=0)
        self.device_menu.add_cascade(label="Output Device", menu=self.output_menu)
        self._populate_output_devices()

        # Output channels submenu
        self.device_menu.add_cascade(
            label="Output Channels", menu=self.output_channels_menu
        )
        self._populate_output_channels(self._initial_output_mapping)

    def _populate_input_devices(self) -> None:
        self.input_menu.delete(0, tk.END)
        selected = self.input_var.get()
        has_match = False
        device_manager = get_device_manager()
        for dev in device_manager.get_input_devices():
            idx = dev["index"]
            self.input_menu.add_radiobutton(
                label=device_manager.format_device_label(dev),
                variable=self.input_var,
                value=idx,
                command=lambda i=idx: self._on_select_input(i),
            )
            if idx == selected:
                has_match = True
        # If selected device not found, clear selection to none
        if not has_match:
            self.input_var.set(-1)
        # Update channels submenu to reflect current selected device capabilities
        self._populate_input_channels(None)

    def _populate_output_devices(self) -> None:
        self.output_menu.delete(0, tk.END)
        selected = self.output_var.get()
        has_match = False
        device_manager = get_device_manager()
        for dev in device_manager.get_output_devices():
            idx = dev["index"]
            self.output_menu.add_radiobutton(
                label=device_manager.format_device_label(dev),
                variable=self.output_var,
                value=idx,
                command=lambda i=idx: self._on_select_output(i),
            )
            if idx == selected:
                has_match = True
        if not has_match:
            self.output_var.set(-1)
        self._populate_output_channels(None)

    def _populate_input_channels(self, initial_mapping: Optional[list]) -> None:
        self.input_channels_menu.delete(0, tk.END)
        # Default option (no explicit mapping)
        self.input_channels_menu.add_radiobutton(
            label="Device default",
            value="default",
            variable=self.input_channels_var,
            command=lambda: self._on_select_input_channels(None),
        )
        # Determine available channels from selected device
        selected_idx = self.input_var.get()
        max_ch = 0
        device_manager = get_device_manager()
        for dev in device_manager.get_input_devices():
            if dev["index"] == selected_idx:
                max_ch = int(dev.get("max_input_channels") or 0)
                break
        # Mono choices
        if max_ch > 0:
            mono_menu = tk.Menu(self.input_channels_menu, tearoff=0)
            for ch in range(max_ch):
                mono_menu.add_radiobutton(
                    label=f"CH {ch+1}",
                    variable=self.input_channels_var,
                    value=f"mono:{ch}",
                    command=lambda c=ch: self._on_select_input_channels([c]),
                )
            self.input_channels_menu.add_cascade(label="Mono", menu=mono_menu)
        # Stereo pairs
        if max_ch >= 2:
            stereo_menu = tk.Menu(self.input_channels_menu, tearoff=0)
            for start in range(0, max_ch - 1, 2):
                stereo_menu.add_radiobutton(
                    label=f"Stereo {start+1}–{start+2}",
                    variable=self.input_channels_var,
                    value=f"stereo:{start}",
                    command=lambda s=start: self._on_select_input_channels([s, s + 1]),
                )
            self.input_channels_menu.add_cascade(label="Stereo", menu=stereo_menu)

    def _populate_output_channels(self, initial_mapping: Optional[list]) -> None:
        self.output_channels_menu.delete(0, tk.END)
        self.output_channels_menu.add_radiobutton(
            label="Device default",
            value="default",
            variable=self.output_channels_var,
            command=lambda: self._on_select_output_channels(None),
        )
        selected_idx = self.output_var.get()
        max_ch = 0
        device_manager = get_device_manager()
        for dev in device_manager.get_output_devices():
            if dev["index"] == selected_idx:
                max_ch = int(dev.get("max_output_channels") or 0)
                break
        # Mono routing to a specific output channel
        if max_ch > 0:
            for ch in range(max_ch):
                self.output_channels_menu.add_radiobutton(
                    label=f"CH {ch+1}",
                    variable=self.output_channels_var,
                    value=f"mono:{ch}",
                    command=lambda c=ch: self._on_select_output_channels([c]),
                )

    def refresh(self) -> None:
        """Re-enumerate devices and rebuild submenus."""
        # Rebuild submenus in place
        self._populate_input_devices()
        self._populate_output_devices()

    def _on_rescan(self) -> None:
        # Try to force PortAudio to refresh device list
        device_manager = get_device_manager()
        device_manager.refresh()
        # Optionally dump devices in debug mode
        if self.debug:
            device_manager.debug_dump_devices()
        # Rebuild menus
        self.refresh()

    def _on_select_input(self, index: int) -> None:
        self.input_var.set(index)
        if self.on_select_input:
            try:
                self.on_select_input(index)
            except Exception:
                pass
        # When device changes, rebuild channels submenu to match capabilities
        self._populate_input_channels(None)

    def _on_select_output(self, index: int) -> None:
        self.output_var.set(index)
        if self.on_select_output:
            try:
                self.on_select_output(index)
            except Exception:
                pass
        self._populate_output_channels(None)

    def _on_select_input_channels(self, mapping: Optional[list]) -> None:
        if self.on_select_input_channels:
            try:
                self.on_select_input_channels(mapping)
            except Exception:
                pass

    def _on_select_output_channels(self, mapping: Optional[list]) -> None:
        if self.on_select_output_channels:
            try:
                self.on_select_output_channels(mapping)
            except Exception:
                pass
