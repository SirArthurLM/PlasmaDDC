"""DDC GUI safety regressions. All backends and preferences are simulated."""

import os
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, call, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import app
from backend import MonitorSummary, PlasmaDDCError, VCPValue


class AsyncDDCChecks(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.backend = Mock()
        self.monitor = MonitorSummary(
            0, 1, 4, "/dev/i2c-4", None, "GSM", "Simulated display", None, "Monitor 1"
        )
        self.backend.refresh_monitors.return_value = [self.monitor]
        self.patches = [
            patch("app.QSettings", side_effect=lambda *_: QSettings(
                str(Path(self.temp.name) / "settings.ini"), QSettings.IniFormat
            )),
            patch("app.PlasmaDDCBackend", return_value=self.backend),
        ]
        for p in self.patches:
            p.start()
        self.window = app.MainWindow()

    def tearDown(self):
        # Tests always release waiting threads before closing the window.
        self.wait_until(lambda: not self.window._ddc_busy)
        self.window.close()
        self.window.deleteLater()
        self.qapp.processEvents()
        for p in reversed(self.patches):
            p.stop()
        self.temp.cleanup()

    def wait_until(self, condition, timeout=3):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.qapp.processEvents()
            time.sleep(0.005)
        self.qapp.processEvents()
        self.assertTrue(condition(), "Worker completion timed out")

    def test_window_opens_without_any_hardware_reads(self):
        self.backend.refresh_monitors.assert_not_called()
        self.backend.build_monitor_profile.assert_not_called()
        self.backend.get_brightness.assert_not_called()
        self.assertFalse(self.window.reload_button.isEnabled())
        self.assertFalse(self.window.capabilities_button.isEnabled())
        self.assertFalse(self.window.getvcp_all_button.isEnabled())

    def test_detection_is_async_and_does_not_read_vcps(self):
        gate = threading.Event()
        running = threading.Event()

        def detect():
            running.set()
            if not gate.wait(timeout=2):
                raise RuntimeError("test timed out")
            return [self.monitor]

        self.backend.refresh_monitors.side_effect = detect
        self.window._hardware_authorized = True
        try:
            self.assertTrue(self.window._submit_ddc(
                self.backend.refresh_monitors,
                self.window._detection_finished,
                "simulated detection",
                needs_monitor=False,
            ))
            self.assertTrue(running.wait(timeout=2))
            self.assertTrue(self.window._ddc_busy)
            self.assertFalse(self.window.centralWidget().isEnabled())
            self.assertEqual(self.window.monitor_combo.count(), 0)
            gate.set()
            self.wait_until(lambda: not self.window._ddc_busy)
            self.assertEqual(self.window.monitor_combo.count(), 1)
            self.backend.build_monitor_profile.assert_not_called()
        finally:
            gate.set()

    def test_only_one_ddc_operation_at_once(self):
        gate = threading.Event()
        started = threading.Event()

        def detect():
            started.set()
            gate.wait(timeout=2)
            return [self.monitor]

        self.backend.refresh_monitors.side_effect = detect
        self.window._hardware_authorized = True
        try:
            self.assertTrue(self.window._submit_ddc(
                self.backend.refresh_monitors,
                self.window._detection_finished,
                "done", needs_monitor=False,
            ))
            self.assertTrue(started.wait(timeout=2))
            self.assertFalse(self.window._submit_ddc(
                self.backend.refresh_monitors,
                self.window._detection_finished,
                "again", needs_monitor=False,
            ))
            gate.set()
            self.wait_until(lambda: not self.window._ddc_busy)
            self.backend.refresh_monitors.assert_called_once()
        finally:
            gate.set()

    def test_worker_thread_different_from_ui_and_callback_in_ui(self):
        ui_thread = threading.get_ident()
        threads = []
        self.window._hardware_authorized = True
        self.assertTrue(self.window._submit_ddc(
            lambda: threading.get_ident(),
            lambda worker_tid: threads.append((worker_tid, threading.get_ident())),
            "done", needs_monitor=False,
        ))
        self.wait_until(lambda: bool(threads))
        self.assertNotEqual(threads[0][0], ui_thread)
        self.assertEqual(threads[0][1], ui_thread)

    def test_language_change_does_not_refresh_ddc(self):
        self.window._detection_finished([self.monitor])
        self.window._remember_value(0, "brightness", VCPValue(0x10, "Brightness", 70, 100))
        self.backend.reset_mock()
        self.window.set_language_preference("es")
        self.window.set_language_preference("en")
        self.backend.refresh_monitors.assert_not_called()
        self.backend.get_brightness.assert_not_called()
        self.backend.build_monitor_profile.assert_not_called()
        self.assertTrue(self.window.brightness_control.read_button.isEnabled())

    def test_single_read_updates_cache_without_bulk_calls(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.backend.get_brightness.return_value = VCPValue(0x10, "Brightness", 70, 100)
        self.window.read_brightness()
        self.wait_until(lambda: not self.window._ddc_busy)
        self.backend.get_brightness.assert_called_once_with(0)
        self.backend.build_monitor_profile.assert_not_called()
        self.assertEqual(self.window.brightness_control.spin.value(), 70)
        self.assertTrue(self.window.contrast_control.read_button.isEnabled())
        self.window.load_current_monitor()
        self.backend.build_monitor_profile.assert_not_called()


    def test_single_reads_unlock_editors_and_apply_buttons(self):
        """Real VCP values unlock editing; the simulated backend is not written."""
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True

        controls = (
            ("brightness", "get_brightness", "read_brightness", 0x10, 85),
            ("contrast", "get_contrast", "read_contrast", 0x12, 60),
            ("volume", "get_volume", "read_volume", 0x62, 42),
        )
        for control_name, getter_name, read_name, vcp, current in controls:
            control = getattr(self.window, f"{control_name}_control")
            with self.subTest(control=control_name):
                self.assertTrue(control.read_button.isEnabled())
                self.assertFalse(control.slider.isEnabled())
                self.assertFalse(control.spin.isEnabled())
                self.assertFalse(control.apply_button.isEnabled())

                getattr(self.backend, getter_name).return_value = VCPValue(
                    vcp, control_name, current, 100
                )
                getattr(self.window, read_name)()
                self.wait_until(lambda: not self.window._ddc_busy)

                self.assertEqual(control.value(), current)
                self.assertTrue(control.slider.isEnabled())
                self.assertTrue(control.spin.isEnabled())
                self.assertTrue(control.apply_button.isEnabled())
                self.assertTrue(control.read_button.isEnabled())

        self.backend.set_brightness.assert_not_called()
        self.backend.set_contrast.assert_not_called()
        self.backend.set_volume.assert_not_called()

    def test_undetected_controls_remain_locked_after_other_read(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.backend.get_brightness.return_value = VCPValue(0x10, "Brightness", 85, 100)
        self.window.read_brightness()
        self.wait_until(lambda: not self.window._ddc_busy)

        for control in (self.window.contrast_control, self.window.volume_control):
            self.assertFalse(control.slider.isEnabled())
            self.assertFalse(control.spin.isEnabled())
            self.assertFalse(control.apply_button.isEnabled())
            self.assertTrue(control.read_button.isEnabled())

    def test_language_switch_keeps_editors_unlocked_without_hardware_io(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.backend.get_brightness.return_value = VCPValue(0x10, "Brightness", 85, 100)
        self.window.read_brightness()
        self.wait_until(lambda: not self.window._ddc_busy)
        self.backend.reset_mock()

        self.window.set_language_preference("es")
        self.window.set_language_preference("en")

        self.assertTrue(self.window.brightness_control.slider.isEnabled())
        self.assertTrue(self.window.brightness_control.spin.isEnabled())
        self.assertTrue(self.window.brightness_control.apply_button.isEnabled())
        self.assertEqual(self.window.brightness_control.value(), 85)
        self.backend.get_brightness.assert_not_called()
        self.backend.refresh_monitors.assert_not_called()



    def test_unread_controls_show_placeholders_not_fake_values(self):
        self.window._detection_finished([self.monitor])
        for control in (self.window.brightness_control, self.window.contrast_control,
                        self.window.volume_control):
            self.assertNotEqual(control.spin.text(), "0")
            self.assertFalse(control.apply_button.isEnabled())
            self.assertTrue(control.read_button.isEnabled())
        self.assertEqual(self.window.input_combo.currentIndex(), -1)
        self.assertEqual(self.window.color_preset_combo.currentIndex(), -1)
        self.backend.get_brightness.assert_not_called()

    def test_valid_zero_is_displayed_after_explicit_read(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.backend.get_brightness.return_value = VCPValue(0x10, "Brightness", 0, 100)
        self.window.read_brightness()
        self.wait_until(lambda: not self.window._ddc_busy)
        self.assertEqual(self.window.brightness_control.spin.text(), "0")
        self.assertTrue(self.window.brightness_control.apply_button.isEnabled())

    def test_color_preset_verify_error_warns_without_automatic_second_operation(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.backend.get_color_preset.return_value = VCPValue(
            0x14, "Select color preset", selector=0x06, label="7500 K"
        )
        self.window.read_color_preset()
        self.wait_until(lambda: not self.window._ddc_busy)
        self.backend.reset_mock()
        self.backend.set_color_preset.side_effect = PlasmaDDCError(
            "Verification failed for feature 14\nTry errors: DDCRC_VERIFY"
        )
        errors = []
        self.window.show_error = errors.append  # Avoid a modal QMessageBox in tests.
        self.window.color_preset_combo.setCurrentIndex(
            self.window.color_preset_combo.findData(0x04)
        )
        with patch("app.QMessageBox.warning", return_value=app.QMessageBox.Yes):
            self.window.apply_color_preset()
            self.wait_until(lambda: not self.window._ddc_busy)
        self.backend.set_color_preset.assert_called_once_with(0, 0x04)
        self.backend.get_color_preset.assert_not_called()
        self.assertEqual(len(errors), 1)
        self.assertIn("DDCRC_VERIFY", errors[0])
        self.assertIn("PlasmaDDC", errors[0])


    def test_picture_section_reads_only_two_values_in_order(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        calls = []
        self.backend.get_brightness.side_effect = lambda index: (
            calls.append("brightness") or VCPValue(0x10, "Brightness", 82, 100)
        )
        self.backend.get_contrast.side_effect = lambda index: (
            calls.append("contrast") or VCPValue(0x12, "Contrast", 61, 100)
        )
        with patch("app.QMessageBox.warning", return_value=app.QMessageBox.Yes), patch(
            "app.time.sleep"
        ) as delay:
            self.window.read_picture_section()
            self.wait_until(lambda: not self.window._ddc_busy)
        self.assertEqual(calls, ["brightness", "contrast"])
        self.assertEqual(delay.call_args_list.count(call(0.25)), 1)
        self.assertEqual(self.window.brightness_control.value(), 82)
        self.assertEqual(self.window.contrast_control.value(), 61)
        self.backend.get_color_preset.assert_not_called()
        self.backend.get_capabilities_text.assert_not_called()
        self.backend.get_all_vcps_text.assert_not_called()
        self.backend.set_brightness.assert_not_called()

    def test_section_cancellation_does_not_access_hardware(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        with patch("app.QMessageBox.warning", return_value=app.QMessageBox.No):
            self.window.read_color_section()
        self.backend.get_color_preset.assert_not_called()
        self.backend.get_rgb_gain.assert_not_called()
        self.assertFalse(self.window._ddc_busy)

    def test_section_error_is_localized_to_failed_control(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.backend.get_brightness.return_value = VCPValue(0x10, "Brightness", 50, 100)
        self.backend.get_contrast.side_effect = PlasmaDDCError("Not supported")
        with patch("app.QMessageBox.warning", return_value=app.QMessageBox.Yes), patch(
            "app.time.sleep"
        ):
            self.window.read_picture_section()
            self.wait_until(lambda: not self.window._ddc_busy)
        self.assertEqual(self.window.brightness_control.value(), 50)
        self.assertFalse(self.window.contrast_control.apply_button.isEnabled())
        self.assertTrue(self.window.contrast_control.read_button.isEnabled())
        self.assertIn("Not supported", self.window.current_profile.errors["contrast"])
        self.backend.get_color_preset.assert_not_called()

    def test_toolbar_section_only_reads_active_page_and_language_does_not_read(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.assertFalse(self.window.reload_button.isEnabled())  # Overview
        self.window.sidebar.setCurrentRow(3)  # Audio
        self.assertTrue(self.window.reload_button.isEnabled())
        self.backend.get_volume.return_value = VCPValue(0x62, "Volume", 25, 100)
        self.window.load_current_monitor()
        self.wait_until(lambda: not self.window._ddc_busy)
        self.backend.get_volume.assert_called_once_with(0)
        self.backend.get_brightness.assert_not_called()
        self.backend.reset_mock()
        self.window.set_language_preference("en")
        self.window.set_language_preference("es")
        self.assertEqual(self.window.sidebar.currentRow(), 3)
        self.assertTrue(self.window.reload_button.isEnabled())
        self.backend.get_volume.assert_not_called()
        self.backend.get_capabilities_text.assert_not_called()

    def test_advanced_diagnostics_require_confirmation_and_preserve_cache(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.assertTrue(self.window.capabilities_button.isEnabled())
        self.assertTrue(self.window.getvcp_all_button.isEnabled())
        with patch("app.QMessageBox.warning", return_value=app.QMessageBox.No):
            self.window.read_capabilities()
            self.window.read_getvcp_all()
        self.backend.get_capabilities_text.assert_not_called()
        self.backend.get_all_vcps_text.assert_not_called()
        self.backend.get_capabilities_text.return_value = "fake capabilities"
        self.backend.get_all_vcps_text.return_value = "fake getvcp all"
        with patch("app.QMessageBox.warning", return_value=app.QMessageBox.Yes):
            self.window.read_capabilities()
            self.wait_until(lambda: not self.window._ddc_busy)
            self.window.read_getvcp_all()
            self.wait_until(lambda: not self.window._ddc_busy)
        self.backend.get_capabilities_text.assert_called_once_with(0)
        self.backend.get_all_vcps_text.assert_called_once_with(0)
        self.assertIn("fake capabilities", self.window.diagnostics_text.toPlainText())
        self.assertIn("fake getvcp all", self.window.diagnostics_text.toPlainText())
        self.backend.get_brightness.assert_not_called()

    def test_partial_diagnostic_output_uses_text_panel_not_error_dialog(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.backend.get_all_vcps_text.return_value = (
            "WARNING: ddcutil exited with code 7; this output may be incomplete.\n"
            "VCP code 0x10 (Brightness): 100"
        )
        errors = []
        self.window.show_error = errors.append
        with patch("app.QMessageBox.warning", return_value=app.QMessageBox.Yes) as confirm:
            self.window.read_getvcp_all()
            self.wait_until(lambda: not self.window._ddc_busy)
        confirm.assert_called_once()  # Only the requested advanced-operation consent.
        self.assertEqual(errors, [])
        self.assertIn("this output may be incomplete", self.window.diagnostics_text.toPlainText())
        self.assertIn("VCP code 0x10", self.window.diagnostics_text.toPlainText())
        self.backend.get_all_vcps_text.assert_called_once_with(0)
        self.backend.get_capabilities_text.assert_not_called()
        self.backend.get_brightness.assert_not_called()

    def test_generic_preset_requires_confirmation_without_extra_reads(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.backend.get_color_preset.return_value = VCPValue(
            0x14, "Select color preset", selector=0x06, label="7500 K"
        )
        self.window.read_color_preset()
        self.wait_until(lambda: not self.window._ddc_busy)
        self.window.color_preset_combo.setCurrentIndex(
            self.window.color_preset_combo.findData(0x04)
        )
        self.backend.reset_mock()
        with patch("app.QMessageBox.warning", return_value=app.QMessageBox.No):
            self.window.apply_color_preset()
        self.backend.set_color_preset.assert_not_called()
        self.backend.get_color_preset.assert_not_called()

    def test_rgb_verify_error_avoids_automatic_retry_or_read(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.backend.set_rgb_gain.side_effect = PlasmaDDCError(
            "Verification failed for feature 16\nTry errors: DDCRC_VERIFY"
        )
        errors = []
        self.window.show_error = errors.append
        self.window.apply_red(41)
        self.wait_until(lambda: not self.window._ddc_busy)
        self.backend.set_rgb_gain.assert_called_once_with(0, "red", 41)
        self.backend.get_rgb_gain.assert_not_called()
        self.assertEqual(len(errors), 1)
        self.assertIn("DDCRC_VERIFY", errors[0])
        self.assertIn("RGB", errors[0])

    def test_color_section_reads_exactly_four_controls(self):
        self.window._detection_finished([self.monitor])
        self.window._hardware_authorized = True
        self.backend.get_color_preset.return_value = VCPValue(
            0x14, "Preset", selector=0x06, label="7500 K"
        )
        self.backend.get_rgb_gain.side_effect = lambda index, channel: VCPValue(
            {"red": 0x16, "green": 0x18, "blue": 0x1A}[channel], channel, 50, 100
        )
        with patch("app.QMessageBox.warning", return_value=app.QMessageBox.Yes), patch(
            "app.time.sleep"
        ) as sleep:
            self.window.read_color_section()
            self.wait_until(lambda: not self.window._ddc_busy)
        self.backend.get_color_preset.assert_called_once_with(0)
        self.assertEqual(self.backend.get_rgb_gain.call_count, 3)
        self.assertEqual(sleep.call_args_list.count(call(0.25)), 3)
        self.backend.get_capabilities_text.assert_not_called()
        self.backend.get_all_vcps_text.assert_not_called()



if __name__ == "__main__":
    unittest.main()
