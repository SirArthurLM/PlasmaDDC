#!/usr/bin/env python3
from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from i18n import _


# =============================================================================
# Importación opcional de monitorcontrol
# =============================================================================

try:
    from monitorcontrol import get_monitors
    from monitorcontrol.vcp import VCPError, VCPIOError, VCPPermissionError

    MONITORCONTROL_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    MONITORCONTROL_IMPORT_ERROR = exc
    get_monitors = None

    class VCPError(Exception):
        pass

    class VCPIOError(Exception):
        pass

    class VCPPermissionError(Exception):
        pass


# =============================================================================
# Códigos VCP comunes
# =============================================================================

VCP_BRIGHTNESS = 0x10
VCP_CONTRAST = 0x12
VCP_COLOR_PRESET = 0x14
VCP_RED_GAIN = 0x16
VCP_GREEN_GAIN = 0x18
VCP_BLUE_GAIN = 0x1A
VCP_INPUT_SOURCE = 0x60
VCP_AUDIO_VOLUME = 0x62

COMMON_VCPS: dict[str, int] = {
    "brightness": VCP_BRIGHTNESS,
    "contrast": VCP_CONTRAST,
    "color_preset": VCP_COLOR_PRESET,
    "red_gain": VCP_RED_GAIN,
    "green_gain": VCP_GREEN_GAIN,
    "blue_gain": VCP_BLUE_GAIN,
    "input_source": VCP_INPUT_SOURCE,
    "volume": VCP_AUDIO_VOLUME,
}

RGB_GAIN_CODES: dict[str, int] = {
    "red": VCP_RED_GAIN,
    "rojo": VCP_RED_GAIN,
    "r": VCP_RED_GAIN,
    "green": VCP_GREEN_GAIN,
    "verde": VCP_GREEN_GAIN,
    "g": VCP_GREEN_GAIN,
    "blue": VCP_BLUE_GAIN,
    "azul": VCP_BLUE_GAIN,
    "b": VCP_BLUE_GAIN,
}

COMMON_INPUT_SOURCES: dict[str, int] = {
    "VGA1": 0x01,
    "VGA 1": 0x01,
    "VGA2": 0x02,
    "VGA 2": 0x02,
    "DVI1": 0x03,
    "DVI 1": 0x03,
    "DVI2": 0x04,
    "DVI 2": 0x04,
    "DP1": 0x0F,
    "DP 1": 0x0F,
    "DISPLAYPORT1": 0x0F,
    "DISPLAYPORT 1": 0x0F,
    "DP2": 0x10,
    "DP 2": 0x10,
    "DISPLAYPORT2": 0x10,
    "DISPLAYPORT 2": 0x10,
    "HDMI1": 0x11,
    "HDMI 1": 0x11,
    "HDMI-1": 0x11,
    "HDMI2": 0x12,
    "HDMI 2": 0x12,
    "HDMI-2": 0x12,
}

KNOWN_COLOR_PRESETS: dict[int, str] = {
    0x01: "sRGB",
    0x02: "Display native",
    0x03: "4000 K",
    0x04: "5000 K",
    0x05: "6500 K",
    0x06: "7500 K",
    0x07: "8200 K",
    0x08: "9300 K",
    0x09: "10000 K",
    0x0A: "11500 K",
    0x0B: "User 1",
    0x0C: "User 2",
    0x0D: "User 3",
}


# =============================================================================
# Errores propios
# =============================================================================

class PlasmaDDCError(RuntimeError):
    pass


class DDCUtilUnavailableError(PlasmaDDCError):
    pass


class MonitorControlUnavailableError(PlasmaDDCError):
    pass


class MonitorNotFoundError(PlasmaDDCError):
    pass


class DDCPermissionError(PlasmaDDCError):
    pass


class VCPUnsupportedError(PlasmaDDCError):
    pass


class BackendMode(str, Enum):
    AUTO = "auto"
    DDCUTIL = "ddcutil"
    MONITORCONTROL = "monitorcontrol"


# =============================================================================
# Modelos de datos
# =============================================================================

@dataclass(frozen=True)
class MonitorSummary:
    index: int
    display_number: int | None
    bus_number: int | None
    bus_path: str | None
    drm_connector: str | None
    manufacturer_id: str | None
    model_name: str | None
    serial_number: str | None
    label: str
    raw_block: str = ""


@dataclass(frozen=True)
class VCPValue:
    code: int
    name: str | None = None
    current: int | None = None
    maximum: int | None = None
    selector: int | None = None
    label: str | None = None
    supported: bool = True
    raw_output: str = ""
    backend: str = "ddcutil"

    @property
    def code_hex(self) -> str:
        return f"0x{self.code:02X}"

    @property
    def numeric_value(self) -> int | None:
        if self.current is not None:
            return self.current
        if self.selector is not None:
            return self.selector
        return None

    def as_text(self) -> str:
        if not self.supported:
            return _("{self_code_hex}: unsupported").format(self_code_hex=self.code_hex)

        if self.current is not None and self.maximum is not None:
            return f"{self.code_hex}: {self.current}/{self.maximum}"

        if self.selector is not None:
            if self.label:
                return f"{self.code_hex}: {self.label} ({self.selector:#04x})"
            return f"{self.code_hex}: {self.selector:#04x}"

        if self.current is not None:
            return f"{self.code_hex}: {self.current}"

        if self.label:
            return f"{self.code_hex}: {self.label}"

        return _("{self_code_hex}: no parsed value").format(self_code_hex=self.code_hex)


@dataclass
class MonitorProfile:
    monitor: MonitorSummary
    values: dict[str, VCPValue] = field(default_factory=dict)
    errors: dict[str, str] = field(default_factory=dict)
    capabilities_text: str | None = None
    getvcp_all_text: str | None = None

    def supported(self, key: str) -> bool:
        return key in self.values and self.values[key].supported


# =============================================================================
# Utilidades de parseo y normalización
# =============================================================================

def normalize_vcp_code(code: int | str) -> int:
    if isinstance(code, int):
        value = code
    else:
        text = str(code).strip().lower()

        if text.startswith("0x"):
            value = int(text, 16)
        elif text.startswith("x"):
            value = int(text[1:], 16)
        else:
            # En ddcutil, los códigos VCP se escriben normalmente en hexadecimal.
            # Por tanto "10" significa 0x10, no decimal 10.
            value = int(text, 16)

    if value < 0 or value > 0xFF:
        raise ValueError(_("VCP code out of range: {code}").format(code=code))

    return value


def format_vcp_code(code: int | str) -> str:
    return f"0x{normalize_vcp_code(code):02X}"


def normalize_percent(value: int, name: str = "value") -> int:
    value = int(value)

    if value < 0 or value > 100:
        raise ValueError(
            _("{name} must be between 0 and 100. Received: {value}").format(name=_(name), value=value)
        )

    return value


def parse_number(text: str) -> int:
    value = text.strip().lower().rstrip(",;)")
    value = value.removeprefix("(")

    if value.startswith("0x"):
        return int(value, 16)

    if value.startswith("x"):
        return int(value[1:], 16)

    return int(value, 10)


def input_source_to_int(value: int | str) -> int:
    if isinstance(value, int):
        return value

    text = str(value).strip()

    if not text:
        raise ValueError(_("Empty video input."))

    upper = text.upper()

    if upper in COMMON_INPUT_SOURCES:
        return COMMON_INPUT_SOURCES[upper]

    return normalize_vcp_code(text)


def input_source_label(value: int) -> str:
    reverse: dict[int, str] = {
        0x01: "VGA-1",
        0x02: "VGA-2",
        0x03: "DVI-1",
        0x04: "DVI-2",
        0x0F: "DisplayPort-1",
        0x10: "DisplayPort-2",
        0x11: "HDMI-1",
        0x12: "HDMI-2",
    }

    return reverse.get(value, f"Input 0x{value:02X}")


def color_preset_label(value: int) -> str:
    return KNOWN_COLOR_PRESETS.get(value, f"Color preset 0x{value:02X}")


def parse_ddcutil_getvcp_output(code: int | str, output: str) -> VCPValue:
    normalized_code = normalize_vcp_code(code)

    # Ejemplos:
    # VCP code 0x10 (Brightness): current value = 100, max value = 100
    # VCP code 0x14 (Select color preset): 6500 K (sl=0x05)
    # VCP code 0x60 (Input Source): HDMI-1 (sl=0x11)
    # VCP code 0x62 (Audio speaker volume): current value = 100, max value = 100

    feature_name: str | None = None
    current: int | None = None
    maximum: int | None = None
    selector: int | None = None
    label: str | None = None

    name_match = re.search(r"VCP code\s+0x[0-9a-fA-F]+\s+\((.*?)\)", output)
    if name_match:
        feature_name = " ".join(name_match.group(1).split())

    current_match = re.search(
        r"current value\s*=\s*(0x[0-9a-fA-F]+|x[0-9a-fA-F]+|\d+)",
        output,
    )
    max_match = re.search(
        r"max(?:imum)? value\s*=\s*(0x[0-9a-fA-F]+|x[0-9a-fA-F]+|\d+)",
        output,
    )
    selector_match = re.search(
        r"\bsl\s*=\s*(0x[0-9a-fA-F]+|x[0-9a-fA-F]+|\d+)",
        output,
    )

    if current_match:
        current = parse_number(current_match.group(1))

    if max_match:
        maximum = parse_number(max_match.group(1))

    if selector_match:
        selector = parse_number(selector_match.group(1))

        # Intentar sacar etiqueta antes de "(sl=...)"
        after_colon = output.split("):", 1)
        if len(after_colon) == 2:
            possible_label = after_colon[1].split("(sl=", 1)[0].strip()
            if possible_label:
                label = possible_label

    if normalized_code == VCP_INPUT_SOURCE and selector is not None:
        label = label or input_source_label(selector)

    if normalized_code == VCP_COLOR_PRESET and selector is not None:
        label = label or color_preset_label(selector)

    supported = "unsupported" not in output.lower()

    return VCPValue(
        code=normalized_code,
        name=feature_name,
        current=current,
        maximum=maximum,
        selector=selector,
        label=label,
        supported=supported,
        raw_output=output,
        backend="ddcutil",
    )


def parse_ddcutil_detect_output(output: str) -> list[MonitorSummary]:
    monitors: list[MonitorSummary] = []

    # Separar bloques empezando por "Display N"
    matches = list(re.finditer(r"(?m)^Display\s+(\d+)", output))

    for pos, match in enumerate(matches):
        display_number = int(match.group(1))
        start = match.start()
        end = matches[pos + 1].start() if pos + 1 < len(matches) else len(output)
        block = output[start:end].strip()

        bus_path = None
        bus_number = None
        drm_connector = None
        manufacturer_id = None
        model_name = None
        serial_number = None

        bus_match = re.search(r"I2C bus:\s*(/dev/i2c-(\d+))", block)
        if bus_match:
            bus_path = bus_match.group(1)
            bus_number = int(bus_match.group(2))

        drm_match = re.search(r"DRM connector:\s*(.+)", block)
        if drm_match:
            drm_connector = drm_match.group(1).strip()

        mfg_match = re.search(r"Mfg id:\s*(.+)", block)
        if mfg_match:
            manufacturer_id = mfg_match.group(1).strip()

        model_match = re.search(r"Model:\s*(.+)", block)
        if model_match:
            model_name = model_match.group(1).strip()

        serial_match = re.search(r"Serial number:\s*(.+)", block)
        if serial_match:
            serial_number = serial_match.group(1).strip()

        label_parts: list[str] = [f"Display {display_number}"]

        if model_name:
            label_parts.append(model_name)

        if drm_connector:
            label_parts.append(drm_connector)

        if bus_path:
            label_parts.append(bus_path)

        monitors.append(
            MonitorSummary(
                index=len(monitors),
                display_number=display_number,
                bus_number=bus_number,
                bus_path=bus_path,
                drm_connector=drm_connector,
                manufacturer_id=manufacturer_id,
                model_name=model_name,
                serial_number=serial_number,
                label=" · ".join(label_parts),
                raw_block=block,
            )
        )

    return monitors


# =============================================================================
# Runner ddcutil
# =============================================================================

class DDCUtilRunner:
    def __init__(self, timeout: int = 20) -> None:
        self.path = shutil.which("ddcutil")
        self.timeout = timeout

    def available(self) -> bool:
        return self.path is not None

    def require_available(self) -> None:
        if not self.available():
            raise DDCUtilUnavailableError(_("ddcutil is not installed or is not in PATH."))

    def _selection_args(
        self,
        display_number: int | None = None,
        bus_number: int | None = None,
    ) -> list[str]:
        if bus_number is not None:
            return ["--bus", str(bus_number)]

        if display_number is not None:
            return ["--display", str(display_number)]

        return []

    def run(
        self,
        command: str,
        args: list[str] | None = None,
        display_number: int | None = None,
        bus_number: int | None = None,
        timeout: int | None = None,
    ) -> str:
        self.require_available()

        args = args or []

        # ddcutil permite display-selection-options en comandos como getvcp/setvcp.
        full_cmd = [
            str(self.path),
            command,
            *self._selection_args(display_number=display_number, bus_number=bus_number),
            *args,
        ]

        try:
            completed = subprocess.run(
                full_cmd,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout or self.timeout,
            )
        except subprocess.TimeoutExpired as exc:
            raise PlasmaDDCError(
                _("ddcutil timed out running: {join_full_cmd}").format(
                    join_full_cmd=" ".join(full_cmd)
                )
            ) from exc
        except OSError as exc:
            raise DDCUtilUnavailableError(str(exc)) from exc

        output = ((completed.stdout or "") + (completed.stderr or "")).strip()

        if completed.returncode != 0:
            lowered = output.lower()

            if (
                "permission" in lowered
                or "denied" in lowered
                or "permiso" in lowered
                or "access" in lowered
            ):
                raise DDCPermissionError(output or _("Permission denied using ddcutil."))

            if "unsupported" in lowered or "not supported" in lowered:
                raise VCPUnsupportedError(output)

            raise PlasmaDDCError(
                output
                or _("ddcutil failed: {join_full_cmd}").format(join_full_cmd=" ".join(full_cmd))
            )

        return output

    def detect(self) -> str:
        return self.run("detect", timeout=30)

    def capabilities(
        self,
        display_number: int | None = None,
        bus_number: int | None = None,
    ) -> str:
        return self.run(
            "capabilities",
            display_number=display_number,
            bus_number=bus_number,
            timeout=30,
        )

    def get_vcp(
        self,
        code: int | str,
        display_number: int | None = None,
        bus_number: int | None = None,
    ) -> VCPValue:
        code_text = format_vcp_code(code)

        output = self.run(
            "getvcp",
            [code_text],
            display_number=display_number,
            bus_number=bus_number,
        )

        return parse_ddcutil_getvcp_output(code_text, output)

    def get_vcp_all(
        self,
        display_number: int | None = None,
        bus_number: int | None = None,
    ) -> str:
        return self.run(
            "getvcp",
            ["all"],
            display_number=display_number,
            bus_number=bus_number,
            timeout=45,
        )

    def set_vcp(
        self,
        code: int | str,
        value: int | str,
        display_number: int | None = None,
        bus_number: int | None = None,
        no_verify: bool = False,
        permit_unknown: bool = False,
    ) -> str:
        code_text = format_vcp_code(code)

        args: list[str] = []

        if permit_unknown:
            args.append("--permit-unknown-feature")

        if no_verify:
            args.append("--noverify")

        args.extend([code_text, str(value)])

        return self.run(
            "setvcp",
            args,
            display_number=display_number,
            bus_number=bus_number,
            timeout=30,
        )


# =============================================================================
# Backend principal PlasmaDDC
# =============================================================================

class PlasmaDDCBackend:
    def __init__(self, mode: BackendMode | str = BackendMode.AUTO) -> None:
        self.mode = BackendMode(mode)
        self.ddcutil = DDCUtilRunner()
        self._ddc_monitors: list[MonitorSummary] = []
        self._monitorcontrol_monitors: list[Any] = []
        self._monitorcontrol_reliable: dict[int, bool] = {}

    # -------------------------------------------------------------------------
    # Disponibilidad
    # -------------------------------------------------------------------------

    def ddcutil_available(self) -> bool:
        return self.ddcutil.available()

    def monitorcontrol_available(self) -> bool:
        return MONITORCONTROL_IMPORT_ERROR is None and get_monitors is not None

    def require_monitorcontrol(self) -> None:
        if not self.monitorcontrol_available():
            raise MonitorControlUnavailableError(
                _("monitorcontrol is unavailable: {MONITORCONTROL_IMPORT_ERROR}").format(
                    MONITORCONTROL_IMPORT_ERROR=MONITORCONTROL_IMPORT_ERROR
                )
            )

    # -------------------------------------------------------------------------
    # Detección de monitores
    # -------------------------------------------------------------------------

    def refresh_monitors(self) -> list[MonitorSummary]:
        self._ddc_monitors = []

        if self.ddcutil_available():
            try:
                raw_detect = self.ddcutil.detect()
                self._ddc_monitors = parse_ddcutil_detect_output(raw_detect)
            except Exception:
                self._ddc_monitors = []

        if self.monitorcontrol_available():
            try:
                self._monitorcontrol_monitors = list(get_monitors())
            except Exception:
                self._monitorcontrol_monitors = []
        else:
            self._monitorcontrol_monitors = []

        if self._ddc_monitors:
            return self._ddc_monitors

        # Fallback: si ddcutil detect no dio bloques pero monitorcontrol sí detecta,
        # creamos summaries mínimos.
        if self._monitorcontrol_monitors:
            return [
                MonitorSummary(
                    index=i,
                    display_number=i + 1,
                    bus_number=None,
                    bus_path=None,
                    drm_connector=None,
                    manufacturer_id=None,
                    model_name=None,
                    serial_number=None,
                    label=f"Monitor {i + 1}",
                    raw_block=repr(mon),
                )
                for i, mon in enumerate(self._monitorcontrol_monitors)
            ]

        return []

    def list_monitors(self) -> list[MonitorSummary]:
        if not self._ddc_monitors and not self._monitorcontrol_monitors:
            return self.refresh_monitors()

        if self._ddc_monitors:
            return self._ddc_monitors

        return [
            MonitorSummary(
                index=i,
                display_number=i + 1,
                bus_number=None,
                bus_path=None,
                drm_connector=None,
                manufacturer_id=None,
                model_name=None,
                serial_number=None,
                label=f"Monitor {i + 1}",
                raw_block=repr(mon),
            )
            for i, mon in enumerate(self._monitorcontrol_monitors)
        ]

    def _get_monitor_summary(self, index: int) -> MonitorSummary:
        monitors = self.list_monitors()

        if index < 0 or index >= len(monitors):
            raise MonitorNotFoundError(
                _("No monitor exists with index {index}").format(index=index)
            )

        return monitors[index]

    def _display_number(self, index: int) -> int | None:
        return self._get_monitor_summary(index).display_number or (index + 1)

    def _bus_number(self, index: int) -> int | None:
        return self._get_monitor_summary(index).bus_number

    def _ddc_select(self, index: int) -> dict[str, int | None]:
        monitor = self._get_monitor_summary(index)
        return {
            "display_number": monitor.display_number or (index + 1),
            "bus_number": monitor.bus_number,
        }

    # -------------------------------------------------------------------------
    # monitorcontrol auxiliar
    # -------------------------------------------------------------------------

    def _get_monitorcontrol_monitor(self, index: int) -> Any:
        self.require_monitorcontrol()

        if not self._monitorcontrol_monitors:
            self._monitorcontrol_monitors = list(get_monitors())

        if index < 0 or index >= len(self._monitorcontrol_monitors):
            raise MonitorNotFoundError(
                _("monitorcontrol has no monitor with index {index}").format(index=index)
            )

        return self._monitorcontrol_monitors[index]

    def _monitorcontrol_call(self, index: int, method_name: str, *args: Any) -> Any:
        monitor = self._get_monitorcontrol_monitor(index)

        try:
            with monitor:
                method = getattr(monitor, method_name)
                return method(*args)
        except VCPPermissionError as exc:
            raise DDCPermissionError(_("monitorcontrol does not have DDC/CI permissions.")) from exc
        except (VCPError, VCPIOError) as exc:
            raise VCPUnsupportedError(
                _("monitorcontrol failed in {method_name}: {exc}").format(
                    method_name=method_name, exc=exc
                )
            ) from exc
        except AttributeError as exc:
            raise PlasmaDDCError(
                _("monitorcontrol has no method {method_name}").format(method_name=method_name)
            ) from exc
        except Exception as exc:
            raise PlasmaDDCError(
                _("monitorcontrol failed in {method_name}: {exc}").format(
                    method_name=method_name, exc=exc
                )
            ) from exc

    def test_monitorcontrol_reliability(self, index: int = 0) -> bool:
        if not self.monitorcontrol_available():
            self._monitorcontrol_reliable[index] = False
            return False

        try:
            self._monitorcontrol_call(index, "get_luminance")
            self._monitorcontrol_reliable[index] = True
            return True
        except Exception:
            self._monitorcontrol_reliable[index] = False
            return False

    def monitorcontrol_reliable(self, index: int = 0) -> bool:
        if index not in self._monitorcontrol_reliable:
            return self.test_monitorcontrol_reliability(index)
        return self._monitorcontrol_reliable[index]

    # -------------------------------------------------------------------------
    # Lectura capabilities/getvcp all
    # -------------------------------------------------------------------------

    def detect_text(self) -> str:
        return self.ddcutil.detect()

    def get_capabilities_text(self, index: int = 0) -> str:
        sel = self._ddc_select(index)
        return self.ddcutil.capabilities(**sel)

    def get_all_vcps_text(self, index: int = 0) -> str:
        sel = self._ddc_select(index)
        return self.ddcutil.get_vcp_all(**sel)

    def get_vcp(self, index: int, code: int | str) -> VCPValue:
        sel = self._ddc_select(index)
        return self.ddcutil.get_vcp(code, **sel)

    def set_vcp(
        self,
        index: int,
        code: int | str,
        value: int | str,
        no_verify: bool = False,
        permit_unknown: bool = False,
    ) -> str:
        sel = self._ddc_select(index)

        return self.ddcutil.set_vcp(
            code=code,
            value=value,
            no_verify=no_verify,
            permit_unknown=permit_unknown,
            **sel,
        )

    def read_known_vcps(self, index: int = 0) -> dict[str, VCPValue]:
        values: dict[str, VCPValue] = {}

        for key, code in COMMON_VCPS.items():
            try:
                values[key] = self.get_vcp(index, code)
            except Exception:
                pass

        return values

    def build_monitor_profile(self, index: int = 0) -> MonitorProfile:
        monitor = self._get_monitor_summary(index)
        profile = MonitorProfile(monitor=monitor)

        try:
            profile.capabilities_text = self.get_capabilities_text(index)
        except Exception as exc:
            profile.errors["capabilities"] = str(exc)

        try:
            profile.getvcp_all_text = self.get_all_vcps_text(index)
        except Exception as exc:
            profile.errors["getvcp_all"] = str(exc)

        for key, code in COMMON_VCPS.items():
            try:
                profile.values[key] = self.get_vcp(index, code)
            except Exception as exc:
                profile.errors[key] = str(exc)

        return profile

    # -------------------------------------------------------------------------
    # API de alto nivel basada principalmente en ddcutil
    # -------------------------------------------------------------------------

    def get_brightness(self, index: int = 0) -> VCPValue:
        return self.get_vcp(index, VCP_BRIGHTNESS)

    def set_brightness(self, index: int, value: int) -> str:
        return self.set_vcp(index, VCP_BRIGHTNESS, normalize_percent(value, _("brightness")))

    def get_contrast(self, index: int = 0) -> VCPValue:
        return self.get_vcp(index, VCP_CONTRAST)

    def set_contrast(self, index: int, value: int) -> str:
        return self.set_vcp(index, VCP_CONTRAST, normalize_percent(value, _("contrast")))

    def get_volume(self, index: int = 0) -> VCPValue:
        return self.get_vcp(index, VCP_AUDIO_VOLUME)

    def set_volume(self, index: int, value: int) -> str:
        return self.set_vcp(index, VCP_AUDIO_VOLUME, normalize_percent(value, _("volume")))

    def get_color_preset(self, index: int = 0) -> VCPValue:
        return self.get_vcp(index, VCP_COLOR_PRESET)

    def set_color_preset(self, index: int, value: int | str) -> str:
        raw_value = normalize_vcp_code(value) if isinstance(value, str) else int(value)
        return self.set_vcp(index, VCP_COLOR_PRESET, f"0x{raw_value:02X}")

    def get_input_source(self, index: int = 0) -> VCPValue:
        return self.get_vcp(index, VCP_INPUT_SOURCE)

    def set_input_source(self, index: int, value: int | str) -> str:
        raw_value = input_source_to_int(value)

        # Con Input Source 0x60 algunos monitores cambian de entrada y ya no se
        # puede verificar el valor desde la misma señal. Por eso usamos no_verify.
        return self.set_vcp(
            index=index,
            code=VCP_INPUT_SOURCE,
            value=f"0x{raw_value:02X}",
            no_verify=True,
        )

    def get_rgb_gain(self, index: int, color: str) -> VCPValue:
        key = color.strip().lower()

        if key not in RGB_GAIN_CODES:
            raise ValueError(_("Invalid RGB color: {color}").format(color=color))

        return self.get_vcp(index, RGB_GAIN_CODES[key])

    def set_rgb_gain(self, index: int, color: str, value: int) -> str:
        key = color.strip().lower()

        if key not in RGB_GAIN_CODES:
            raise ValueError(_("Invalid RGB color: {color}").format(color=color))

        return self.set_vcp(
            index=index,
            code=RGB_GAIN_CODES[key],
            value=normalize_percent(value, _("gain {color}").format(color=color)),
        )

    # -------------------------------------------------------------------------
    # API auxiliar monitorcontrol, por si queremos compararla o usarla en casos
    # donde funcione mejor que ddcutil.
    # -------------------------------------------------------------------------

    def get_brightness_monitorcontrol(self, index: int = 0) -> int:
        return int(self._monitorcontrol_call(index, "get_luminance"))

    def set_brightness_monitorcontrol(self, index: int, value: int) -> None:
        self._monitorcontrol_call(index, "set_luminance", normalize_percent(value))

    def get_contrast_monitorcontrol(self, index: int = 0) -> int:
        return int(self._monitorcontrol_call(index, "get_contrast"))

    def set_contrast_monitorcontrol(self, index: int, value: int) -> None:
        self._monitorcontrol_call(index, "set_contrast", normalize_percent(value))

    def get_volume_monitorcontrol(self, index: int = 0) -> int:
        return int(self._monitorcontrol_call(index, "get_volume"))

    def set_volume_monitorcontrol(self, index: int, value: int) -> None:
        self._monitorcontrol_call(index, "set_volume", normalize_percent(value))

    def get_input_source_monitorcontrol(self, index: int = 0) -> int:
        return int(self._monitorcontrol_call(index, "get_input_source"))

    def set_input_source_monitorcontrol(self, index: int, value: int | str) -> None:
        self._monitorcontrol_call(index, "set_input_source", input_source_to_int(value))


# =============================================================================
# Smoke test
# =============================================================================

def smoke_test() -> int:
    backend = PlasmaDDCBackend()

    print(_("PlasmaDDC backend v2 - quick test"))
    print()
    print(_("Main backend: ddcutil"))
    print(_("Auxiliary backend: monitorcontrol"))
    print()
    print(_("ddcutil available:"), backend.ddcutil_available())
    print(_("monitorcontrol available:"), backend.monitorcontrol_available())
    print()

    monitors = backend.refresh_monitors()

    if not monitors:
        print(_("No monitors detected."))
        return 1

    print(_("Monitors detected by PlasmaDDC: {len_monitors}").format(len_monitors=len(monitors)))

    for monitor in monitors:
        print()
        print(f"[{monitor.index}] {monitor.label}")
        print(f"  display_number: {monitor.display_number}")
        print(f"  bus_number: {monitor.bus_number}")
        print(f"  bus_path: {monitor.bus_path}")
        print(f"  drm_connector: {monitor.drm_connector}")
        print(f"  model_name: {monitor.model_name}")

        mc_ok = backend.monitorcontrol_reliable(monitor.index)
        print(_("  monitorcontrol reliable for basic VCP controls: {mc_ok}").format(mc_ok=mc_ok))

        print()
        print(_("  Common VCP controls via ddcutil:"))

        for key, code in COMMON_VCPS.items():
            try:
                value = backend.get_vcp(monitor.index, code)
                print(f"    {key:14s} {value.as_text()}")

                if key == "input_source" and value.selector is not None:
                    print(
                        _(
                            "                  normalized label: {input_source_label_value_selector}"
                        ).format(
                            input_source_label_value_selector=input_source_label(value.selector)
                        )
                    )

                if key == "color_preset" and value.selector is not None:
                    print(
                        _(
                            "                  normalized label: {color_preset_label_value_selector}"
                        ).format(
                            color_preset_label_value_selector=color_preset_label(value.selector)
                        )
                    )

            except Exception as exc:
                print(_("    {key:14s} unavailable ({exc})").format(key=key, exc=exc))

    return 0


if __name__ == "__main__":
    raise SystemExit(smoke_test())
