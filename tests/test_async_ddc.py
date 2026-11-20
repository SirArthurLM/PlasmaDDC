"""DDC GUI safety regressions. All backends and preferences are simulated."""

import os
import threading
import time
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import app
from backend import MonitorSummary, VCPValue


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



if __name__ == "__main__":
    unittest.main()
