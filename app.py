#!/usr/bin/env python3
from __future__ import annotations

import sys
from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import QLocale, QSettings, Qt
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from i18n import _, language_manager

from backend import (
    COMMON_INPUT_SOURCES,
    COMMON_VCPS,
    PlasmaDDCBackend,
    PlasmaDDCError,
    VCPValue,
    color_preset_label,
    input_source_label,
    input_source_to_int,
)


APP_NAME = "PlasmaDDC"


class LanguagePreferencesDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("Language preferences"))
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.language_combo = QComboBox()
        self.language_combo.addItem(_("System default"), "system")
        self.language_combo.addItem("English", "en")
        self.language_combo.addItem("Español", "es")
        self.language_combo.setCurrentIndex(
            self.language_combo.findData(language_manager.preference)
        )
        form.addRow(_("Language:"), self.language_combo)
        layout.addLayout(form)
        description = QLabel(
            _(
                "System default follows your desktop language. "
                "Unsupported languages use English. Changes take effect immediately."
            )
        )
        description.setWordWrap(True)
        layout.addWidget(description)
        buttons = QDialogButtonBox()
        buttons.addButton(_("Cancel"), QDialogButtonBox.RejectRole)
        buttons.addButton(_("OK"), QDialogButtonBox.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def selected_language(self) -> str:
        return str(self.language_combo.currentData())


@dataclass(frozen=True)
class PageInfo:
    title: str
    subtitle: str


def unique_input_sources() -> list[tuple[str, int]]:
    seen: set[int] = set()
    result: list[tuple[str, int]] = []

    for _, value in sorted(COMMON_INPUT_SOURCES.items(), key=lambda item: item[1]):
        if value in seen:
            continue
        seen.add(value)
        result.append((input_source_label(value), value))

    return result


def common_color_presets() -> list[tuple[str, int]]:
    return [(color_preset_label(value), value) for value in range(1, 14)]


class ValueControl(QWidget):
    def __init__(
        self,
        title: str,
        apply_callback: Callable[[int], None],
        read_callback: Callable[[], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self.title = title
        self.apply_callback = apply_callback
        self.read_callback = read_callback

        self.name_label = QLabel(title)
        self.name_label.setMinimumWidth(130)

        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 100)
        self.slider.setSingleStep(1)
        self.slider.setPageStep(5)

        self.spin = QSpinBox()
        self.spin.setRange(0, 100)
        self.spin.setMinimumWidth(80)

        self.apply_button = QPushButton(_("Apply"))
        self.read_button = QPushButton(_("Read"))
        self.status_label = QLabel("")
        self.status_label.setWordWrap(True)

        self.slider.valueChanged.connect(self.spin.setValue)
        self.spin.valueChanged.connect(self.slider.setValue)
        self.apply_button.clicked.connect(self.apply)
        self.read_button.clicked.connect(self.read)

        top = QHBoxLayout()
        top.addWidget(self.name_label)
        top.addWidget(self.slider, 1)
        top.addWidget(self.spin)
        top.addWidget(self.apply_button)
        top.addWidget(self.read_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 8)
        layout.addLayout(top)
        layout.addWidget(self.status_label)

    def set_value(self, value: VCPValue) -> None:
        current = value.current
        maximum = value.maximum or 100

        if current is None:
            self.set_unavailable(_("No numeric value could be parsed."))
            return

        self.slider.blockSignals(True)
        self.spin.blockSignals(True)

        self.slider.setRange(0, maximum)
        self.spin.setRange(0, maximum)
        self.slider.setValue(current)
        self.spin.setValue(current)

        self.slider.blockSignals(False)
        self.spin.blockSignals(False)

        self.setEnabled(True)

        if value.name:
            self.status_label.setText(f"{value.name} · {current}/{maximum} · {value.backend}")
        else:
            self.status_label.setText(f"{current}/{maximum} · {value.backend}")

    def set_unavailable(self, reason: str) -> None:
        self.setEnabled(False)
        self.status_label.setText(_("Unavailable: {reason}").format(reason=reason))

    def value(self) -> int:
        return int(self.spin.value())

    def apply(self) -> None:
        self.apply_callback(self.value())

    def read(self) -> None:
        if self.read_callback is not None:
            self.read_callback()


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()

        self.settings = QSettings(APP_NAME, APP_NAME)
        language_manager.configure(
            self.settings.value("language", "system", type=str),
            QLocale.system().name(),
        )
        self.backend = PlasmaDDCBackend()
        self.monitors = []
        self.current_profile = None

        self.setWindowTitle(APP_NAME)
        self.resize(1040, 720)

        self._build_ui()
        self._build_menu()
        self.refresh_monitors()

    # ------------------------------------------------------------------
    # UI base
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        central = QWidget()
        root = QVBoxLayout(central)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        header = self._build_header()
        root.addWidget(header)

        splitter = QSplitter(Qt.Horizontal)

        self.sidebar = QListWidget()
        self.sidebar.setMinimumWidth(190)
        self.sidebar.setMaximumWidth(260)
        self.sidebar.currentRowChanged.connect(self._change_page)

        self.stack = QStackedWidget()

        splitter.addWidget(self.sidebar)
        splitter.addWidget(self.stack)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)

        root.addWidget(splitter, 1)

        self.setCentralWidget(central)
        self.statusBar().showMessage(_("Ready"))

        self._create_pages()

    def _build_header(self) -> QWidget:
        box = QFrame()
        box.setFrameShape(QFrame.StyledPanel)

        layout = QHBoxLayout(box)
        layout.setContentsMargins(12, 10, 12, 10)

        title_box = QVBoxLayout()
        title = QLabel(APP_NAME)
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        subtitle = QLabel(_("Monitor control through DDC/CI"))
        subtitle.setStyleSheet("opacity: 0.75;")
        title_box.addWidget(title)
        title_box.addWidget(subtitle)

        self.monitor_combo = QComboBox()
        self.monitor_combo.setMinimumWidth(340)
        self.monitor_combo.currentIndexChanged.connect(self.load_current_monitor)

        self.refresh_button = QPushButton(_("Detect monitors"))
        self.reload_button = QPushButton(_("Read values"))
        self.refresh_button.clicked.connect(self.refresh_monitors)
        self.reload_button.clicked.connect(self.load_current_monitor)

        layout.addLayout(title_box, 1)
        layout.addWidget(QLabel("Monitor:"))
        layout.addWidget(self.monitor_combo)
        layout.addWidget(self.refresh_button)
        layout.addWidget(self.reload_button)

        return box

    def _build_menu(self) -> None:
        app_menu = self.menuBar().addMenu("PlasmaDDC")
        refresh_action = QAction(_("Read values"), app_menu)
        refresh_action.triggered.connect(self.load_current_monitor)

        detect_action = QAction(_("Detect monitors"), app_menu)
        detect_action.triggered.connect(self.refresh_monitors)

        quit_action = QAction(_("Quit"), app_menu)
        quit_action.triggered.connect(self.close)

        app_menu.addAction(refresh_action)
        app_menu.addAction(detect_action)
        app_menu.addSeparator()
        app_menu.addAction(quit_action)

        preferences_menu = self.menuBar().addMenu(_("Preferences"))
        language_action = QAction(_("Language…"), preferences_menu)
        language_action.triggered.connect(self.show_language_preferences)
        preferences_menu.addAction(language_action)

    def show_language_preferences(self) -> None:
        dialog = LanguagePreferencesDialog(self)
        if dialog.exec() == QDialog.Accepted:
            self.set_language_preference(dialog.selected_language())
        dialog.deleteLater()

    def set_language_preference(self, preference: str) -> None:
        if preference == language_manager.preference:
            return
        language_manager.configure(preference, QLocale.system().name())
        self.settings.setValue("language", language_manager.preference)
        self.settings.sync()

        # Rebuild translated widgets without changing hardware settings. Preserve
        # the selected monitor and page, and re-read localized status/errors.
        page = self.sidebar.currentRow()
        monitor_index = self.current_monitor_index()
        old_central = self.takeCentralWidget()
        self._build_ui()
        for action in self.menuBar().actions():
            menu = action.menu()
            if menu is not None:
                menu.deleteLater()
        self.menuBar().clear()
        self._build_menu()
        if old_central is not None:
            old_central.deleteLater()
        self.monitor_combo.blockSignals(True)
        for monitor in self.monitors:
            self.monitor_combo.addItem(monitor.label, monitor.index)
        self.monitor_combo.setCurrentIndex(self.monitor_combo.findData(monitor_index))
        self.monitor_combo.blockSignals(False)
        if self.monitors:
            self.load_current_monitor()
        else:
            self.disable_all_controls(_("No monitors detected."))
            self.overview_label.setText(_("No monitors detected."))
        self.sidebar.setCurrentRow(page)

    def _create_pages(self) -> None:
        pages = [
            (_("Overview"), self._page_overview()),
            (_("Picture"), self._page_image()),
            ("Color", self._page_color()),
            ("Audio", self._page_audio()),
            (_("Input"), self._page_input()),
            (_("Diagnostics"), self._page_diagnostics()),
        ]

        for title, widget in pages:
            item = QListWidgetItem(title)
            self.sidebar.addItem(item)
            self.stack.addWidget(widget)

        self.sidebar.setCurrentRow(0)

    def _page_wrapper(self, info: PageInfo) -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(12)

        title = QLabel(info.title)
        title.setStyleSheet("font-size: 18px; font-weight: 600;")

        subtitle = QLabel(info.subtitle)
        subtitle.setWordWrap(True)

        layout.addWidget(title)
        layout.addWidget(subtitle)

        return page, layout

    def _change_page(self, row: int) -> None:
        if row >= 0:
            self.stack.setCurrentIndex(row)

    # ------------------------------------------------------------------
    # Páginas
    # ------------------------------------------------------------------

    def _page_overview(self) -> QWidget:
        page, layout = self._page_wrapper(
            PageInfo(
                _("Monitor overview"),
                _("Monitor information detected by ddcutil and backend status."),
            )
        )

        group = QGroupBox(_("Current monitor"))
        form = QFormLayout(group)

        self.overview_label = QLabel(_("No monitor selected."))
        self.overview_label.setWordWrap(True)

        self.backend_label = QLabel("")
        self.backend_label.setWordWrap(True)

        form.addRow(_("Information:"), self.overview_label)
        form.addRow("Backends:", self.backend_label)

        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _page_image(self) -> QWidget:
        page, layout = self._page_wrapper(
            PageInfo(
                _("Picture"),
                _("Basic brightness and contrast settings."),
            )
        )

        group = QGroupBox(_("Picture controls"))
        group_layout = QVBoxLayout(group)

        self.brightness_control = ValueControl(
            _("Brightness"),
            self.apply_brightness,
            self.read_brightness,
        )
        self.contrast_control = ValueControl(
            _("Contrast"),
            self.apply_contrast,
            self.read_contrast,
        )

        group_layout.addWidget(self.brightness_control)
        group_layout.addWidget(self.contrast_control)

        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _page_color(self) -> QWidget:
        page, layout = self._page_wrapper(
            PageInfo(
                "Color",
                _("Color temperature preset and RGB gains, where supported by the monitor."),
            )
        )

        preset_group = QGroupBox(_("Temperature / color preset"))
        preset_layout = QHBoxLayout(preset_group)

        self.color_preset_combo = QComboBox()
        for label, value in common_color_presets():
            self.color_preset_combo.addItem(f"{label} · 0x{value:02X}", value)

        self.color_apply_button = QPushButton(_("Apply preset"))
        self.color_read_button = QPushButton(_("Read"))
        self.color_status_label = QLabel("")

        self.color_apply_button.clicked.connect(self.apply_color_preset)
        self.color_read_button.clicked.connect(self.read_color_preset)

        preset_layout.addWidget(self.color_preset_combo, 1)
        preset_layout.addWidget(self.color_apply_button)
        preset_layout.addWidget(self.color_read_button)
        preset_layout.addWidget(self.color_status_label)

        rgb_group = QGroupBox(_("RGB gains"))
        rgb_layout = QVBoxLayout(rgb_group)

        self.red_control = ValueControl(_("Red"), self.apply_red, self.read_red)
        self.green_control = ValueControl(_("Green"), self.apply_green, self.read_green)
        self.blue_control = ValueControl(_("Blue"), self.apply_blue, self.read_blue)

        rgb_layout.addWidget(self.red_control)
        rgb_layout.addWidget(self.green_control)
        rgb_layout.addWidget(self.blue_control)

        layout.addWidget(preset_group)
        layout.addWidget(rgb_group)
        layout.addStretch(1)
        return page

    def _page_audio(self) -> QWidget:
        page, layout = self._page_wrapper(
            PageInfo(
                "Audio",
                _("Monitor speaker/audio output volume, where supported."),
            )
        )

        group = QGroupBox(_("Volume"))
        group_layout = QVBoxLayout(group)

        self.volume_control = ValueControl(
            _("Volume"),
            self.apply_volume,
            self.read_volume,
        )

        group_layout.addWidget(self.volume_control)

        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _page_input(self) -> QWidget:
        page, layout = self._page_wrapper(
            PageInfo(
                _("Video input"),
                _(
                    "Change the input source. Selecting an input without a signal may leave the screen blank."
                ),
            )
        )

        group = QGroupBox("Source / input")
        form = QFormLayout(group)

        self.input_combo = QComboBox()
        for label, value in unique_input_sources():
            self.input_combo.addItem(f"{label} · 0x{value:02X}", value)

        self.input_apply_button = QPushButton(_("Change input"))
        self.input_read_button = QPushButton(_("Read current input"))
        self.input_status_label = QLabel("")
        self.input_status_label.setWordWrap(True)

        buttons = QWidget()
        buttons_layout = QHBoxLayout(buttons)
        buttons_layout.setContentsMargins(0, 0, 0, 0)
        buttons_layout.addWidget(self.input_apply_button)
        buttons_layout.addWidget(self.input_read_button)
        buttons_layout.addStretch(1)

        self.input_apply_button.clicked.connect(self.apply_input_source)
        self.input_read_button.clicked.connect(self.read_input_source)

        form.addRow(_("Input:"), self.input_combo)
        form.addRow("", buttons)
        form.addRow(_("Status:"), self.input_status_label)

        layout.addWidget(group)
        layout.addStretch(1)
        return page

    def _page_diagnostics(self) -> QWidget:
        page, layout = self._page_wrapper(
            PageInfo(
                _("Diagnostics"),
                _("Raw ddcutil capabilities and getvcp all output for troubleshooting."),
            )
        )

        buttons = QHBoxLayout()
        self.capabilities_button = QPushButton(_("Read capabilities"))
        self.getvcp_all_button = QPushButton(_("Read getvcp all"))
        self.clear_diag_button = QPushButton(_("Clear"))

        self.capabilities_button.clicked.connect(self.read_capabilities)
        self.getvcp_all_button.clicked.connect(self.read_getvcp_all)
        self.clear_diag_button.clicked.connect(lambda: self.diagnostics_text.clear())

        buttons.addWidget(self.capabilities_button)
        buttons.addWidget(self.getvcp_all_button)
        buttons.addWidget(self.clear_diag_button)
        buttons.addStretch(1)

        self.diagnostics_text = QTextEdit()
        self.diagnostics_text.setReadOnly(True)
        self.diagnostics_text.setLineWrapMode(QTextEdit.NoWrap)
        self.diagnostics_text.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout.addLayout(buttons)
        layout.addWidget(self.diagnostics_text, 1)
        return page

    # ------------------------------------------------------------------
    # Utilidades de estado
    # ------------------------------------------------------------------

    def current_monitor_index(self) -> int:
        data = self.monitor_combo.currentData()
        if data is None:
            return 0
        return int(data)

    def set_busy(self, busy: bool, message: str = "") -> None:
        self.setEnabled(not busy)
        QApplication.setOverrideCursor(Qt.WaitCursor if busy else Qt.ArrowCursor)

        if not busy:
            QApplication.restoreOverrideCursor()

        if message:
            self.statusBar().showMessage(message)

    def info(self, message: str) -> None:
        self.statusBar().showMessage(message, 7000)

    def show_error(self, message: str) -> None:
        self.statusBar().showMessage(message, 10000)
        QMessageBox.warning(self, APP_NAME, message)

    def run_safe(self, operation: Callable[[], None], success: str | None = None) -> None:
        try:
            operation()
            if success:
                self.info(success)
        except PlasmaDDCError as exc:
            self.show_error(str(exc))
        except Exception as exc:
            self.show_error(_("Unexpected error: {exc}").format(exc=exc))

    def select_combo_by_value(self, combo: QComboBox, value: int) -> None:
        for i in range(combo.count()):
            if int(combo.itemData(i)) == int(value):
                combo.setCurrentIndex(i)
                return

    # ------------------------------------------------------------------
    # Carga de monitores y perfil
    # ------------------------------------------------------------------

    def refresh_monitors(self) -> None:
        def op() -> None:
            self.monitors = self.backend.refresh_monitors()

            self.monitor_combo.blockSignals(True)
            self.monitor_combo.clear()

            for monitor in self.monitors:
                self.monitor_combo.addItem(monitor.label, monitor.index)

            self.monitor_combo.blockSignals(False)

            if self.monitors:
                self.monitor_combo.setCurrentIndex(0)
                self.load_current_monitor()
            else:
                self.disable_all_controls(_("No monitors detected."))
                self.overview_label.setText(_("No monitors detected."))

        self.run_safe(op, _("Monitor list refreshed."))

    def load_current_monitor(self) -> None:
        if not self.monitors:
            return

        def op() -> None:
            index = self.current_monitor_index()
            self.current_profile = self.backend.build_monitor_profile(index)
            self.update_from_profile()

        self.run_safe(op, _("Values read."))

    def disable_all_controls(self, reason: str) -> None:
        for control in (
            self.brightness_control,
            self.contrast_control,
            self.volume_control,
            self.red_control,
            self.green_control,
            self.blue_control,
        ):
            control.set_unavailable(reason)

        self.color_preset_combo.setEnabled(False)
        self.color_apply_button.setEnabled(False)
        self.color_read_button.setEnabled(False)
        self.color_status_label.setText(reason)

        self.input_combo.setEnabled(False)
        self.input_apply_button.setEnabled(False)
        self.input_read_button.setEnabled(False)
        self.input_status_label.setText(reason)

    def update_from_profile(self) -> None:
        if self.current_profile is None:
            return

        profile = self.current_profile
        monitor = profile.monitor

        self.overview_label.setText(
            "\n".join(
                [
                    _("Label: {monitor_label}").format(monitor_label=monitor.label),
                    f"Display: {monitor.display_number}",
                    f"Bus: {monitor.bus_path or monitor.bus_number}",
                    _("DRM connector: {monitor_drm_connector}").format(
                        monitor_drm_connector=monitor.drm_connector
                    ),
                    _("Manufacturer: {monitor_manufacturer_id}").format(
                        monitor_manufacturer_id=monitor.manufacturer_id
                    ),
                    _("Model: {monitor_model_name}").format(monitor_model_name=monitor.model_name),
                    _("Serial: {monitor_serial_number}").format(
                        monitor_serial_number=monitor.serial_number
                    ),
                ]
            )
        )

        self.backend_label.setText(
            "\n".join(
                [
                    _("ddcutil available: {self_backend_ddcutil_available}").format(
                        self_backend_ddcutil_available=self.backend.ddcutil_available()
                    ),
                    _("monitorcontrol available: {value}").format(
                        value=self.backend.monitorcontrol_available()
                    ),
                    _("monitorcontrol reliable for basic VCP controls: {value}").format(
                        value=self.backend.monitorcontrol_reliable(monitor.index)
                    ),
                    _("Active control backend: ddcutil"),
                ]
            )
        )

        self.update_value_control(
            self.brightness_control,
            "brightness",
            _("Brightness unavailable."),
        )
        self.update_value_control(
            self.contrast_control,
            "contrast",
            _("Contrast unavailable."),
        )
        self.update_value_control(
            self.volume_control,
            "volume",
            _("Volume unavailable."),
        )
        self.update_value_control(
            self.red_control,
            "red_gain",
            _("Red unavailable."),
        )
        self.update_value_control(
            self.green_control,
            "green_gain",
            _("Green unavailable."),
        )
        self.update_value_control(
            self.blue_control,
            "blue_gain",
            _("Blue unavailable."),
        )

        self.update_color_preset()
        self.update_input_source()

        diag_parts = []
        if profile.capabilities_text:
            diag_parts.append("===== capabilities =====")
            diag_parts.append(profile.capabilities_text)

        if profile.getvcp_all_text:
            diag_parts.append("")
            diag_parts.append("===== getvcp all =====")
            diag_parts.append(profile.getvcp_all_text)

        if profile.errors:
            diag_parts.append("")
            diag_parts.append(_("===== errors/unavailable controls ====="))
            for key, value in profile.errors.items():
                diag_parts.append(f"{key}: {value}")

        self.diagnostics_text.setPlainText("\n".join(diag_parts))

    def update_value_control(self, control: ValueControl, key: str, fallback: str) -> None:
        if self.current_profile is None:
            control.set_unavailable(_("No profile loaded."))
            return

        value = self.current_profile.values.get(key)

        if value is not None:
            control.set_value(value)
            return

        reason = self.current_profile.errors.get(key, fallback)
        control.set_unavailable(reason)

    def update_color_preset(self) -> None:
        if self.current_profile is None:
            return

        value = self.current_profile.values.get("color_preset")

        if value is None:
            self.color_preset_combo.setEnabled(False)
            self.color_apply_button.setEnabled(False)
            self.color_read_button.setEnabled(False)
            self.color_status_label.setText(
                self.current_profile.errors.get("color_preset", _("Unavailable."))
            )
            return

        self.color_preset_combo.setEnabled(True)
        self.color_apply_button.setEnabled(True)
        self.color_read_button.setEnabled(True)

        if value.selector is not None:
            self.select_combo_by_value(self.color_preset_combo, value.selector)
            self.color_status_label.setText(value.as_text())
        else:
            self.color_status_label.setText(value.as_text())

    def update_input_source(self) -> None:
        if self.current_profile is None:
            return

        value = self.current_profile.values.get("input_source")

        if value is None:
            self.input_combo.setEnabled(False)
            self.input_apply_button.setEnabled(False)
            self.input_read_button.setEnabled(False)
            self.input_status_label.setText(
                self.current_profile.errors.get("input_source", _("Unavailable."))
            )
            return

        self.input_combo.setEnabled(True)
        self.input_apply_button.setEnabled(True)
        self.input_read_button.setEnabled(True)

        if value.selector is not None:
            self.select_combo_by_value(self.input_combo, value.selector)
            self.input_status_label.setText(value.as_text())
        else:
            self.input_status_label.setText(value.as_text())

    # ------------------------------------------------------------------
    # Lecturas individuales
    # ------------------------------------------------------------------

    def read_brightness(self) -> None:
        self.run_safe(
            lambda: self.brightness_control.set_value(
                self.backend.get_brightness(self.current_monitor_index())
            ),
            _("Brightness read."),
        )

    def read_contrast(self) -> None:
        self.run_safe(
            lambda: self.contrast_control.set_value(
                self.backend.get_contrast(self.current_monitor_index())
            ),
            _("Contrast read."),
        )

    def read_volume(self) -> None:
        self.run_safe(
            lambda: self.volume_control.set_value(
                self.backend.get_volume(self.current_monitor_index())
            ),
            _("Volume read."),
        )

    def read_red(self) -> None:
        self.run_safe(
            lambda: self.red_control.set_value(
                self.backend.get_rgb_gain(self.current_monitor_index(), "red")
            ),
            _("Red gain read."),
        )

    def read_green(self) -> None:
        self.run_safe(
            lambda: self.green_control.set_value(
                self.backend.get_rgb_gain(self.current_monitor_index(), "green")
            ),
            _("Green gain read."),
        )

    def read_blue(self) -> None:
        self.run_safe(
            lambda: self.blue_control.set_value(
                self.backend.get_rgb_gain(self.current_monitor_index(), "blue")
            ),
            _("Blue gain read."),
        )

    def read_color_preset(self) -> None:
        def op() -> None:
            value = self.backend.get_color_preset(self.current_monitor_index())
            if value.selector is not None:
                self.select_combo_by_value(self.color_preset_combo, value.selector)
            self.color_status_label.setText(value.as_text())

        self.run_safe(op, _("Color preset read."))

    def read_input_source(self) -> None:
        def op() -> None:
            value = self.backend.get_input_source(self.current_monitor_index())
            if value.selector is not None:
                self.select_combo_by_value(self.input_combo, value.selector)
            self.input_status_label.setText(value.as_text())

        self.run_safe(op, _("Input read."))

    def read_capabilities(self) -> None:
        def op() -> None:
            text = self.backend.get_capabilities_text(self.current_monitor_index())
            self.diagnostics_text.setPlainText(text)

        self.run_safe(op, _("Capabilities read."))

    def read_getvcp_all(self) -> None:
        def op() -> None:
            text = self.backend.get_all_vcps_text(self.current_monitor_index())
            self.diagnostics_text.setPlainText(text)

        self.run_safe(op, _("getvcp all read."))

    # ------------------------------------------------------------------
    # Escrituras
    # ------------------------------------------------------------------

    def apply_brightness(self, value: int) -> None:
        self.run_safe(
            lambda: self.backend.set_brightness(self.current_monitor_index(), value),
            _("Brightness applied: {value}").format(value=value),
        )

    def apply_contrast(self, value: int) -> None:
        self.run_safe(
            lambda: self.backend.set_contrast(self.current_monitor_index(), value),
            _("Contrast applied: {value}").format(value=value),
        )

    def apply_volume(self, value: int) -> None:
        self.run_safe(
            lambda: self.backend.set_volume(self.current_monitor_index(), value),
            _("Volume applied: {value}").format(value=value),
        )

    def apply_red(self, value: int) -> None:
        self.run_safe(
            lambda: self.backend.set_rgb_gain(self.current_monitor_index(), "red", value),
            _("Red gain applied: {value}").format(value=value),
        )

    def apply_green(self, value: int) -> None:
        self.run_safe(
            lambda: self.backend.set_rgb_gain(self.current_monitor_index(), "green", value),
            _("Green gain applied: {value}").format(value=value),
        )

    def apply_blue(self, value: int) -> None:
        self.run_safe(
            lambda: self.backend.set_rgb_gain(self.current_monitor_index(), "blue", value),
            _("Blue gain applied: {value}").format(value=value),
        )

    def apply_color_preset(self) -> None:
        value = int(self.color_preset_combo.currentData())

        self.run_safe(
            lambda: self.backend.set_color_preset(self.current_monitor_index(), value),
            _("Color preset applied: {color_preset_label_value}").format(
                color_preset_label_value=color_preset_label(value)
            ),
        )

        self.read_color_preset()

    def apply_input_source(self) -> None:
        value = int(self.input_combo.currentData())
        label = input_source_label(value)

        answer = QMessageBox.warning(
            self,
            APP_NAME,
            (
                _(
                    "You are about to change the monitor input to:\n\n{label} · 0x{value:02X}\n\nIf that input has no signal, the screen may go blank until you switch back using the physical buttons on the monitor.\n\nDo you want to continue?"
                ).format(label=label, value=value)
            ),
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )

        if answer != QMessageBox.Yes:
            self.info(_("Input change cancelled."))
            return

        self.run_safe(
            lambda: self.backend.set_input_source(self.current_monitor_index(), value),
            _("Input applied: {label}").format(label=label),
        )


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName(APP_NAME)

    window = MainWindow()
    window.show()

    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
