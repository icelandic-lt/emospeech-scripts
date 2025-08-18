"""LED-style vertical level meter widget that reads from SharedState."""

import tkinter as tk
from typing import Optional
import time

from .config import LevelMeterConfig, RecordingStandard, RECORDING_STANDARDS
from ...audio.shared_state import SharedState, SETTINGS_STATUS_VALID


class LEDLevelMeter(tk.Frame):
    """Vertical LED-style audio level meter widget that reads from SharedState."""

    # Visual constants
    METER_WIDTH = 80
    METER_MIN_HEIGHT = 220
    LED_COUNT = 30
    LED_MIN_HEIGHT = 4
    LED_MAX_HEIGHT = 10
    LED_MIN_SPACING = 2
    LED_MAX_SPACING = 4
    LED_X_INSET = 20
    SCALE_WIDTH = 50
    MARGIN = 8
    LED_SPACING_SCALE = 9  # Heuristic scale factor for spacing calculation

    # Non-linear scale to give more resolution in the upper, critical range
    SCALE_PIVOT_DB = -30.0
    SCALE_BOTTOM_FRACTION = (
        0.4  # portion of the meter used for [-60..pivot], top gets the rest
    )

    # Colors
    COLOR_BACKGROUND = "#1e1e1e"
    COLOR_LED_OFF = "#2d2d2d"
    COLOR_OPTIMAL = "#4CAF50"
    COLOR_WARNING = "#FFC107"
    COLOR_DANGER = "#F44336"
    COLOR_LOW = "#2196F3"
    COLOR_RMS = "#FFFFFF"
    COLOR_PEAK = "#FF9800"
    COLOR_TEXT = "#FFFFFF"
    COLOR_GRID = "#444444"
    DIM_FACTOR = 0.25  # Intensity factor for dimming inactive LEDs

    def __init__(
        self,
        parent: tk.Widget,
        shared_state: SharedState,
        config: Optional[LevelMeterConfig] = None,
    ):
        """Initialize LED level meter widget.

        Args:
            parent: Parent tkinter widget
            shared_state: SharedState instance for reading level data
            config: Level meter configuration
        """
        super().__init__(parent, bg=self.COLOR_BACKGROUND)

        self.shared_state = shared_state
        self.config = config or LevelMeterConfig()

        # Level tracking
        self.current_rms = -60.0
        self.current_peak = -60.0
        self.peak_hold_value = -60.0
        self._peak_hold_last_update = time.monotonic()
        self.PEAK_HOLD_MS = 1500  # hold time in milliseconds
        self.PEAK_DECAY_DB_PER_SEC = 10.0
        self.last_frame_count = 0

        # LED elements
        self.leds = []
        self.led_states = [False] * self.LED_COUNT

        # Geometry cache for fast updates
        self._geom_height = self.METER_MIN_HEIGHT
        self._geom_led_height = 8
        self._geom_spacing = 2
        self._geom_start_y = 0

        # Peak-hold line
        self._peak_hold_line_id: Optional[int] = None

        # Control flag to stop scheduling when widget is destroyed
        self._running: bool = True
        self.bind("<Destroy>", lambda e: setattr(self, "_running", False))

        self._create_ui()
        self._schedule_update()

    def refresh(self) -> None:
        """Force a redraw of geometry and display (useful after (re)show)."""
        try:
            self._rebuild_geometry()
            self._update_display()
        except Exception:
            pass

    def _create_ui(self) -> None:
        """Create the LED level meter UI components."""
        # Labels at top (with values)
        self.label_frame = tk.Frame(self, bg=self.COLOR_BACKGROUND)
        self.label_frame.pack(fill=tk.X, padx=2, pady=(2, 5))

        # Peak row (top)
        peak_row = tk.Frame(self.label_frame, bg=self.COLOR_BACKGROUND)
        peak_row.pack(fill=tk.X)
        tk.Label(
            peak_row,
            text="Peak",
            fg=self.COLOR_PEAK,
            bg=self.COLOR_BACKGROUND,
            font=("TkDefaultFont", 9),
        ).pack(side=tk.LEFT)
        self.peak_value_label = tk.Label(
            peak_row,
            text="-- dB",
            fg=self.COLOR_TEXT,
            bg=self.COLOR_BACKGROUND,
            font=("TkDefaultFont", 9),
        )
        self.peak_value_label.pack(side=tk.RIGHT)

        # RMS row (below)
        rms_row = tk.Frame(self.label_frame, bg=self.COLOR_BACKGROUND)
        rms_row.pack(fill=tk.X)
        tk.Label(
            rms_row,
            text="RMS",
            fg=self.COLOR_RMS,
            bg=self.COLOR_BACKGROUND,
            font=("TkDefaultFont", 9),
        ).pack(side=tk.LEFT)
        self.rms_value_label = tk.Label(
            rms_row,
            text="-- dB",
            fg=self.COLOR_TEXT,
            bg=self.COLOR_BACKGROUND,
            font=("TkDefaultFont", 9),
        )
        self.rms_value_label.pack(side=tk.RIGHT)

        # Container frame for meter and scale
        self.meter_container = tk.Frame(self, bg=self.COLOR_BACKGROUND)
        self.meter_container.pack(fill=tk.BOTH, expand=True)

        # LED meter canvas (left side)
        self.canvas = tk.Canvas(
            self.meter_container,
            width=self.METER_WIDTH,
            height=self.METER_MIN_HEIGHT,
            bg=self.COLOR_BACKGROUND,
            highlightthickness=0,
        )
        self.canvas.pack(side=tk.LEFT, padx=(5, 0))

        # Scale canvas (right side)
        self.scale_canvas = tk.Canvas(
            self.meter_container,
            width=self.SCALE_WIDTH,
            height=self.METER_MIN_HEIGHT,
            bg=self.COLOR_BACKGROUND,
            highlightthickness=0,
        )
        self.scale_canvas.pack(side=tk.LEFT, padx=(2, 5))

        # Draw static elements based on current size
        self._rebuild_geometry()

        # Level readout at bottom
        self.level_label = tk.Label(
            self,
            text="-- dB",
            fg=self.COLOR_TEXT,
            bg=self.COLOR_BACKGROUND,
            font=("TkDefaultFont", 12),
        )
        self.level_label.pack(pady=(5, 2))

        # Bind resize of container to adjust canvas heights and rebuild LED layout
        self.bind("<Configure>", self._on_resize)

    def _rebuild_geometry(self) -> None:
        """Rebuild LED layout and scale based on current height."""
        # Determine available height
        height = max(self.METER_MIN_HEIGHT, self.winfo_height() - 50)
        self.canvas.config(height=height)
        self.scale_canvas.config(height=height)

        # Compute LED size/spacing to fit nicely
        available = max(100, height - 2 * self.MARGIN)
        # total = N * (h + s) - s  => choose s within bounds, compute h
        spacing = max(
            self.LED_MIN_SPACING,
            min(
                self.LED_MAX_SPACING,
                int(available / (self.LED_COUNT * self.LED_SPACING_SCALE)),
            ),
        )
        led_height = int(
            (available + spacing - self.LED_COUNT * spacing) / self.LED_COUNT
        )
        led_height = max(self.LED_MIN_HEIGHT, min(self.LED_MAX_HEIGHT, led_height))

        total_led_height = self.LED_COUNT * (led_height + spacing) - spacing
        start_y = (height - total_led_height) / 2

        # Cache geometry
        self._geom_height = height
        self._geom_led_height = led_height
        self._geom_spacing = spacing
        self._geom_start_y = start_y

        # Clear canvas before drawing
        self.canvas.delete("all")

        # Rebuild LEDs
        self.leds.clear()
        for i in range(self.LED_COUNT):
            y = start_y + (self.LED_COUNT - 1 - i) * (led_height + spacing)
            db_value = self._led_index_to_db(i)
            color = self._get_led_color(db_value)
            x0 = self.LED_X_INSET
            x1 = self.METER_WIDTH - self.LED_X_INSET
            led = self.canvas.create_rectangle(
                x0,
                y,
                x1,
                y + led_height,
                fill=self.COLOR_LED_OFF,
                outline=self.COLOR_LED_OFF,
                width=1,
            )
            self.leds.append((led, color))

        # Remove and recreate peak-hold line placeholder
        if self._peak_hold_line_id is not None:
            try:
                self.canvas.delete(self._peak_hold_line_id)
            except Exception:
                pass
        self._peak_hold_line_id = None

        # Rebuild scale
        self.scale_canvas.delete("all")
        self._draw_scale_dynamic(height, led_height, spacing, start_y)

    def _led_index_to_db(self, index: int) -> float:
        """Convert LED index to dB value using non-linear scale."""
        if index <= 0:
            return -60.0
        if index >= self.LED_COUNT - 1:
            return 0.0
        position = index / (self.LED_COUNT - 1)  # 0..1 from bottom to top
        bottom_frac = self.SCALE_BOTTOM_FRACTION
        top_frac = 1.0 - bottom_frac
        if position <= bottom_frac:
            # Map [0..bottom_frac] → [-60..pivot]
            rel = position / bottom_frac if bottom_frac > 0 else 0.0
            return -60.0 + rel * (self.SCALE_PIVOT_DB - (-60.0))
        else:
            # Map (bottom_frac..1] → [pivot..0]
            rel = (position - bottom_frac) / top_frac if top_frac > 0 else 0.0
            return self.SCALE_PIVOT_DB + rel * (0.0 - self.SCALE_PIVOT_DB)

    def _db_to_led_count(self, db: float) -> int:
        """Convert dB value to number of LEDs to light using non-linear scale."""
        if db <= -60.0:
            return 0
        if db >= 0.0:
            return self.LED_COUNT

        bottom_frac = self.SCALE_BOTTOM_FRACTION
        top_frac = 1.0 - bottom_frac

        if db <= self.SCALE_PIVOT_DB:
            # Map [-60..pivot] → [0..bottom_frac]
            rel = (
                (db - (-60.0)) / (self.SCALE_PIVOT_DB - (-60.0))
                if self.SCALE_PIVOT_DB > -60.0
                else 0.0
            )
            position = rel * bottom_frac
        else:
            # Map (pivot..0] → (bottom_frac..1]
            rel = (
                (db - self.SCALE_PIVOT_DB) / (0.0 - self.SCALE_PIVOT_DB)
                if self.SCALE_PIVOT_DB < 0.0
                else 0.0
            )
            position = bottom_frac + rel * top_frac

        # position 0..1 → LED count 0..LED_COUNT
        return int(round(position * (self.LED_COUNT)))

    def _get_led_color(self, db: float) -> str:
        """Get LED color based on dB value."""
        if db >= self.config.danger_level:
            color = self.COLOR_DANGER
        elif db >= self.config.warning_level:
            color = self.COLOR_WARNING
        elif db >= self.config.target_min:
            color = self.COLOR_OPTIMAL
        else:
            color = self.COLOR_LOW

        return color

    def _dim_color(self, color: str, factor: float = 0.25) -> str:
        """Return a dimmed version of a hex color by blending towards background.

        Args:
            color: Hex color string like '#RRGGBB'
            factor: 0..1 intensity (lower = dimmer)

        Returns:
            Hex color string
        """

        def hex_to_rgb(h: str) -> tuple[int, int, int]:
            h = h.lstrip("#")
            return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)

        def rgb_to_hex(r: int, g: int, b: int) -> str:
            return f"#{r:02x}{g:02x}{b:02x}"

        src_r, src_g, src_b = hex_to_rgb(color)
        bg_r, bg_g, bg_b = hex_to_rgb(self.COLOR_BACKGROUND)
        r = int(bg_r + (src_r - bg_r) * max(0.0, min(1.0, factor)))
        g = int(bg_g + (src_g - bg_g) * max(0.0, min(1.0, factor)))
        b = int(bg_b + (src_b - bg_b) * max(0.0, min(1.0, factor)))
        return rgb_to_hex(r, g, b)

    def _draw_scale_dynamic(
        self, height: int, led_height: int, spacing: int, start_y: int
    ) -> None:
        """Draw the dB scale aligned to LED centers with readable fonts."""
        # Adjusted ticks: 0, -6, -12, ... for clearer top range
        db_marks = [0, -6, -12, -18, -24, -30, -40, -50, -60]

        for db in db_marks:
            # place tick at the y of the LED that contains this value
            led_index = min(max(self._db_to_led_count(db) - 1, 0), self.LED_COUNT - 1)
            y = (
                start_y
                + (self.LED_COUNT - 1 - led_index) * (led_height + spacing)
                + led_height / 2
            )
            self.scale_canvas.create_line(0, y, 12, y, fill=self.COLOR_GRID, width=1)
            self.scale_canvas.create_text(
                16,
                y,
                text=str(db),
                fill=self.COLOR_TEXT,
                font=("TkDefaultFont", 10),
                anchor="w",
            )

        # Horizontal target lines on scale
        tmin_idx = self._db_to_led_count(self.config.target_min) - 1
        tmax_idx = self._db_to_led_count(self.config.target_max) - 1
        if 0 <= tmin_idx < self.LED_COUNT:
            y = (
                start_y
                + (self.LED_COUNT - 1 - tmin_idx) * (led_height + spacing)
                + led_height / 2
            )
            # Draw through LED meter only
            self.canvas.create_line(
                self.LED_X_INSET,
                y,
                self.METER_WIDTH - self.LED_X_INSET,
                y,
                fill=self.COLOR_OPTIMAL,
                width=2,
                dash=(3, 2),
            )
        if 0 <= tmax_idx < self.LED_COUNT:
            y = (
                start_y
                + (self.LED_COUNT - 1 - tmax_idx) * (led_height + spacing)
                + led_height / 2
            )
            # Draw through LED meter only
            self.canvas.create_line(
                self.LED_X_INSET,
                y,
                self.METER_WIDTH - self.LED_X_INSET,
                y,
                fill=self.COLOR_OPTIMAL,
                width=2,
                dash=(3, 2),
            )

    def _draw_target_range_indicators(self) -> None:
        """Draw visual indicators for the target range on the scale."""
        # Calculate LED positions for target range
        target_min_index = self._db_to_led_count(self.config.target_min) - 1
        target_max_index = self._db_to_led_count(self.config.target_max) - 1

        # Calculate vertical positions
        total_led_height = (
            self.LED_COUNT * (self.LED_HEIGHT + self.LED_SPACING) - self.LED_SPACING
        )
        start_y = (self.METER_HEIGHT - total_led_height) / 2

        # Draw target min line
        if 0 <= target_min_index < self.LED_COUNT:
            y_min = (
                start_y
                + (self.LED_COUNT - 1 - target_min_index)
                * (self.LED_HEIGHT + self.LED_SPACING)
                + self.LED_HEIGHT / 2
            )
            self.scale_canvas.create_line(
                0,
                y_min,
                self.SCALE_WIDTH,
                y_min,
                fill=self.COLOR_OPTIMAL,
                width=2,
                dash=(3, 2),
            )

        # Draw target max line
        if 0 <= target_max_index < self.LED_COUNT:
            y_max = (
                start_y
                + (self.LED_COUNT - 1 - target_max_index)
                * (self.LED_HEIGHT + self.LED_SPACING)
                + self.LED_HEIGHT / 2
            )
            self.scale_canvas.create_line(
                0,
                y_max,
                self.SCALE_WIDTH,
                y_max,
                fill=self.COLOR_OPTIMAL,
                width=2,
                dash=(3, 2),
            )

    def _schedule_update(self) -> None:
        """Schedule periodic updates from shared state."""
        try:
            self._update_from_shared_state()
        finally:
            # Schedule next update (30 Hz) only if widget is still alive and running
            if self._running and self.winfo_exists():
                self.after(33, self._schedule_update)

    def _update_from_shared_state(self) -> None:
        """Update level meter from shared state data."""
        if not self.shared_state or getattr(self.shared_state, "shm", None) is None:
            return

        # Get level meter state
        try:
            level_state = self.shared_state.get_level_meter_state()
        except Exception:
            # Shared memory likely already torn down during shutdown
            return

        # Check if valid data
        if level_state.get("status", 0) != SETTINGS_STATUS_VALID:
            return

        # Check if data has been updated
        frame_count = level_state.get("frame_count", 0)
        if frame_count == self.last_frame_count:
            return

        self.last_frame_count = frame_count

        # Update levels
        self.current_rms = level_state.get("rms_db", -60.0)
        instant_peak = level_state.get("peak_db", -60.0)
        self.current_peak = instant_peak

        # Update our own peak-hold behavior (simple hold + decay; never below instant peak or RMS)
        now = time.monotonic()
        if instant_peak > self.peak_hold_value:
            self.peak_hold_value = instant_peak
            self._peak_hold_last_update = now
        else:
            elapsed = now - self._peak_hold_last_update
            hold_seconds = self.PEAK_HOLD_MS / 1000.0
            if elapsed > hold_seconds:
                decay = self.PEAK_DECAY_DB_PER_SEC * (elapsed - hold_seconds)
                new_value = self.peak_hold_value - decay
                floor_value = max(instant_peak, self.current_rms)
                self.peak_hold_value = max(-60.0, max(new_value, floor_value))
                # keep last update to now to avoid compounding
                self._peak_hold_last_update = now

        # Update display
        self._update_display()

    def _update_display(self) -> None:
        """Update the LED display."""
        # Calculate how many LEDs to light for RMS
        rms_led_count = self._db_to_led_count(self.current_rms)

        # Calculate peak LED position
        self._db_to_led_count(self.current_peak) - 1

        # Update LEDs
        for i in range(self.LED_COUNT):
            led, _ = self.leds[i]

            # Get current color based on LED position and current config
            db_value = self._led_index_to_db(i)
            color = self._get_led_color(db_value)

            # Light up LEDs up to RMS level; others show dimmed zone color
            if i < rms_led_count:
                self.canvas.itemconfig(led, fill=color)
            else:
                self.canvas.itemconfig(
                    led, fill=self._dim_color(color, self.DIM_FACTOR)
                )

            # Show peak as brighter LED
            # No special LED for peak; peak-hold is a line

        # Update numeric readouts (Peak shows hold value) with color by thresholds
        rms_text = f"{self.current_rms:.1f}" if self.current_rms > -60 else "--"
        peak_text = (
            f"{self.peak_hold_value:.1f}" if self.peak_hold_value > -60 else "--"
        )
        self.rms_value_label.config(text=f"{rms_text} dB")
        self.peak_value_label.config(text=f"{peak_text} dB")

        # Color for numeric labels
        def color_for_value(db: float) -> str:
            if db >= self.config.danger_level:
                return self.COLOR_DANGER
            if db >= self.config.warning_level:
                return self.COLOR_WARNING
            if self.config.target_min <= db <= self.config.target_max:
                return self.COLOR_OPTIMAL
            return self.COLOR_TEXT

        if self.current_rms > -60:
            self.rms_value_label.config(fg=color_for_value(self.current_rms))
        else:
            self.rms_value_label.config(fg=self.COLOR_TEXT)
        if self.peak_hold_value > -60:
            self.peak_value_label.config(fg=color_for_value(self.peak_hold_value))
        else:
            self.peak_value_label.config(fg=self.COLOR_TEXT)
        self.level_label.config(text=f"{rms_text} dB")

        # Update text color based on level
        if self.current_rms >= self.config.danger_level:
            color = self.COLOR_DANGER
        elif self.current_rms >= self.config.warning_level:
            color = self.COLOR_WARNING
        elif self.config.target_min <= self.current_rms <= self.config.target_max:
            color = self.COLOR_OPTIMAL
        else:
            color = self.COLOR_TEXT
        self.level_label.config(fg=color)

        # Draw/update peak-hold line (on the meter canvas) with zone-based color
        if self.peak_hold_value > -60:
            y = self._value_to_y(self.peak_hold_value)
        else:
            y = None
        if y is not None:
            x0, x1 = self.LED_X_INSET, self.METER_WIDTH - self.LED_X_INSET
            # Choose color from the same zone mapping as LEDs (blue/green/yellow/red)
            ph_color = self._get_led_color(self.peak_hold_value)
            if self._peak_hold_line_id is None:
                self._peak_hold_line_id = self.canvas.create_line(
                    x0, y, x1, y, fill=ph_color, width=2
                )
            else:
                self.canvas.coords(self._peak_hold_line_id, x0, y, x1, y)
                self.canvas.itemconfig(self._peak_hold_line_id, fill=ph_color)
        else:
            if self._peak_hold_line_id is not None:
                try:
                    self.canvas.delete(self._peak_hold_line_id)
                except Exception:
                    pass
                self._peak_hold_line_id = None

    def set_standard(self, standard: RecordingStandard) -> None:
        """Set the recording standard preset.

        Args:
            standard: Recording standard to use
        """
        if standard in RECORDING_STANDARDS:
            self.config = RECORDING_STANDARDS[standard]
            # Redraw LEDs with new color zones
            self._rebuild_geometry()

    def set_config(self, config: LevelMeterConfig) -> None:
        """Set custom configuration.

        Args:
            config: Level meter configuration
        """
        self.config = config

        # Rebuild full geometry (LEDs + scale) to reflect new thresholds
        self._rebuild_geometry()

        # Force immediate display update
        self._update_display()

    def get_current_levels(self) -> tuple[float, float]:
        """Get current RMS and peak levels.

        Returns:
            Tuple of (rms_db, peak_db)
        """
        return self.current_rms, self.current_peak

    def is_in_optimal_range(self) -> bool:
        """Check if current RMS level is in optimal range.

        Returns:
            True if in optimal range
        """
        return self.config.target_min <= self.current_rms <= self.config.target_max

    def reset(self) -> None:
        """Reset the level meter."""
        self.current_rms = -60.0
        self.current_peak = -60.0
        self.peak_hold_value = -60.0
        self.last_frame_count = 0
        self._update_display()

    # --- Resize handling ---
    def _on_resize(self, event) -> None:
        """Handle resizing to prevent clipping and keep layout readable."""
        self._rebuild_geometry()

    # --- Helpers ---
    def _value_to_y(self, db_value: float) -> Optional[float]:
        """Map a dB value to Y coordinate (center of the corresponding LED)."""
        if db_value <= -60:
            index = 0
        elif db_value >= 0:
            index = self.LED_COUNT - 1
        else:
            index = self._db_to_led_count(db_value) - 1
        if not (0 <= index < self.LED_COUNT):
            return None
        y = (
            self._geom_start_y
            + (self.LED_COUNT - 1 - index)
            * (self._geom_led_height + self._geom_spacing)
            + self._geom_led_height / 2
        )
        return y
