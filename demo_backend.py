"""Self-contained in-memory monitor backend for PlasmaDDC's explicit --demo mode.

The demo never invokes ddcutil or monitorcontrol operations. It reuses
only passive data types and VCP constants from :mod:`backend`.
"""

from __future__ import annotations

from dataclasses import dataclass
from threading import RLock

from backend import (
    COMMON_VCPS,
    KNOWN_COLOR_PRESETS,
    MonitorProfile,
    MonitorSummary,
    VCPValue,
    color_preset_label,
    input_source_label,
)


@dataclass(frozen=True)
class _DemoMonitor:
    summary: MonitorSummary
    initial: dict[str, int]


class DemoBackend:
    """Imitate the GUI's backend operations with no physical monitor I/O.

    No subprocesses, /dev/i2c access, DDC/CI detection, or real backend object
    are involved.  Values exist only for this application's process lifetime.
    """

    def __init__(self) -> None:
        self._lock = RLock()
        self._monitors = (
            _DemoMonitor(
                MonitorSummary(
                    0, 1, None, None, "SIMULATED-1", "DEMO", "Demo Monitor 1",
                    "DEMO-001", "Demo Monitor 1 — DisplayPort",
                ),
                {
                    "brightness": 70, "contrast": 60, "volume": 45,
                    "red_gain": 50, "green_gain": 50, "blue_gain": 50,
                    "color_preset": 0x05, "input_source": 0x0F,
                },
            ),
            _DemoMonitor(
                MonitorSummary(
                    1, 2, None, None, "SIMULATED-2", "DEMO", "Demo Monitor 2",
                    "DEMO-002", "Demo Monitor 2 — HDMI",
                ),
                {
                    "brightness": 40, "contrast": 55, "volume": 25,
                    "red_gain": 55, "green_gain": 48, "blue_gain": 65,
                    "color_preset": 0x08, "input_source": 0x11,
                },
            ),
        )
        self._state = {m.summary.index: dict(m.initial) for m in self._monitors}

    def ddcutil_available(self) -> bool:
        return False

    def monitorcontrol_available(self) -> bool:
        return False

    def refresh_monitors(self) -> list[MonitorSummary]:
        return [m.summary for m in self._monitors]

    def _read(self, index: int, key: str) -> VCPValue:
        with self._lock:
            value = self._state[index][key]
        code = COMMON_VCPS[key]
        names = {
            "brightness": "Brightness", "contrast": "Contrast",
            "volume": "Audio speaker volume", "red_gain": "Video gain: Red",
            "green_gain": "Video gain: Green", "blue_gain": "Video gain: Blue",
            "color_preset": "Select color preset", "input_source": "Input Source",
        }
        if key in ("color_preset", "input_source"):
            label = color_preset_label(value) if key == "color_preset" else input_source_label(value)
            return VCPValue(code, names[key], selector=value, label=label, backend="demo")
        return VCPValue(code, names[key], value, 100, backend="demo")

    def _write(self, index: int, key: str, value: int) -> VCPValue:
        value = int(value)
        if key in ("color_preset", "input_source"):
            valid = (KNOWN_COLOR_PRESETS if key == "color_preset" else
                     {0x01, 0x02, 0x03, 0x04, 0x0F, 0x10, 0x11, 0x12})
            if value not in valid:
                raise ValueError(f"Unsupported demo selector: {value:#x}")
        elif not 0 <= value <= 100:
            raise ValueError("Demo value must be between 0 and 100")
        with self._lock:
            self._state[index][key] = value
        return self._read(index, key)

    def build_monitor_profile(self, index: int = 0) -> MonitorProfile:
        monitor = next(m.summary for m in self._monitors if m.summary.index == index)
        return MonitorProfile(
            monitor,
            values={key: self._read(index, key) for key in COMMON_VCPS},
        )

    def get_brightness(self, index: int = 0) -> VCPValue:
        return self._read(index, "brightness")

    def set_brightness(self, index: int, value: int) -> VCPValue:
        return self._write(index, "brightness", value)

    def get_contrast(self, index: int = 0) -> VCPValue:
        return self._read(index, "contrast")

    def set_contrast(self, index: int, value: int) -> VCPValue:
        return self._write(index, "contrast", value)

    def get_volume(self, index: int = 0) -> VCPValue:
        return self._read(index, "volume")

    def set_volume(self, index: int, value: int) -> VCPValue:
        return self._write(index, "volume", value)

    def get_rgb_gain(self, index: int, channel: str) -> VCPValue:
        return self._read(index, f"{channel}_gain")

    def set_rgb_gain(self, index: int, channel: str, value: int) -> VCPValue:
        return self._write(index, f"{channel}_gain", value)

    def get_color_preset(self, index: int = 0) -> VCPValue:
        return self._read(index, "color_preset")

    def set_color_preset(self, index: int, value: int) -> VCPValue:
        return self._write(index, "color_preset", value)

    def get_input_source(self, index: int = 0) -> VCPValue:
        return self._read(index, "input_source")

    def set_input_source(self, index: int, value: int) -> VCPValue:
        return self._write(index, "input_source", value)
