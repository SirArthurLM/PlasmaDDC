"""Regression tests: --demo must never attempt actual DDC/CI monitor access."""

import os
import subprocess
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

import app
from demo_backend import DemoBackend
from i18n import language_manager


class DemoBackendTests(unittest.TestCase):
    def test_independent_monitors_and_initial_values(self):
        backend = DemoBackend()
        displays = backend.refresh_monitors()
        self.assertEqual(len(displays), 2)
        self.assertIsNone(displays[0].bus_path)
        self.assertEqual(backend.get_brightness(0).current, 70)
        self.assertEqual(backend.get_brightness(1).current, 40)
        self.assertEqual(backend.get_input_source(0).selector, 0x0F)
        self.assertEqual(backend.get_color_preset(1).selector, 0x08)
        backend.set_brightness(1, 88)
        self.assertEqual(backend.get_brightness(1).current, 88)
        self.assertEqual(backend.get_brightness(0).current, 70)
        self.assertEqual(len(backend.build_monitor_profile(1).values), 8)

    def test_demo_rejects_out_of_range_values(self):
        backend = DemoBackend()
        with self.assertRaises(ValueError):
            backend.set_brightness(0, 101)
        with self.assertRaises(ValueError):
            backend.set_color_preset(0, 0xFF)
        with self.assertRaises(ValueError):
            backend.set_input_source(0, 0xFE)
        with self.assertRaises(KeyError):
            backend.get_volume(404)

    def test_backend_has_no_subprocess_or_hardware_dependency(self):
        with patch("subprocess.run", side_effect=AssertionError("external command")), patch(
            "subprocess.Popen", side_effect=AssertionError("external command")
        ):
            backend = DemoBackend()
            backend.refresh_monitors()
            backend.set_volume(0, 33)
            backend.get_volume(0)
            backend.get_rgb_gain(0, "red")
            backend.set_rgb_gain(1, "blue", 22)
            backend.set_color_preset(0, 0x06)
            backend.set_input_source(0, 0x11)
            backend.build_monitor_profile(0)


class DemoWindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.qapp = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.block_real_backend = patch(
            "app.PlasmaDDCBackend", side_effect=AssertionError("real backend instantiated")
        )
        self.block_subprocess = patch(
            "subprocess.run", side_effect=AssertionError("external process attempted")
        )
        self.block_popen = patch(
            "subprocess.Popen", side_effect=AssertionError("external process attempted")
        )
        self.settings_names = []

        def temporary_settings(*names):
            self.settings_names.append(names)
            return QSettings(str(Path(self.temp.name) / "demo.ini"), QSettings.IniFormat)

        self.settings_patch = patch("app.QSettings", side_effect=temporary_settings)
        self.block_real_backend.start()
        self.block_subprocess.start()
        self.block_popen.start()
        self.settings_patch.start()
        self.window = app.MainWindow(demo_mode=True)

    def tearDown(self):
        self.wait_until(lambda: not self.window._ddc_busy)
        self.window.close()
        self.window.deleteLater()
        self.qapp.processEvents()
        self.settings_patch.stop()
        self.block_popen.stop()
        self.block_subprocess.stop()
        self.block_real_backend.stop()
        self.temp.cleanup()

    def wait_until(self, condition, timeout=3):
        deadline = time.monotonic() + timeout
        while not condition() and time.monotonic() < deadline:
            self.qapp.processEvents()
            time.sleep(0.005)
        self.qapp.processEvents()
        self.assertTrue(condition(), "Demo job timed out")

    def test_demo_starts_with_two_preloaded_monitors_without_hardware(self):
        self.assertTrue(self.window.demo_mode)
        self.assertEqual(self.window.monitor_combo.count(), 2)
        self.assertEqual(self.window.brightness_control.spin.value(), 70)
        self.assertTrue(self.window.brightness_control.isEnabled())
        self.assertTrue(self.window.findChild(type(self.window.overview_label), "demoModeBanner"))
        self.assertIn("DEMO", self.window.windowTitle())
        self.assertFalse(self.window.reload_button.isEnabled())
        self.assertFalse(self.window.getvcp_all_button.isEnabled())

    def test_demo_settings_are_separate_from_normal_settings(self):
        self.assertEqual(self.settings_names[0], ("PlasmaDDC", "PlasmaDDC-Demo"))

    def test_demo_switch_monitor_does_not_mix_values(self):
        self.window.monitor_combo.setCurrentIndex(1)
        self.assertEqual(self.window.brightness_control.spin.value(), 40)
        self.window.monitor_combo.setCurrentIndex(0)
        self.assertEqual(self.window.brightness_control.spin.value(), 70)

    def test_demo_applies_and_reads_brightness_without_real_backend(self):
        self.window.apply_brightness(88)
        self.wait_until(lambda: not self.window._ddc_busy)
        self.assertEqual(self.window.backend.get_brightness(0).current, 88)
        self.assertEqual(self.window.brightness_control.spin.value(), 88)
        self.window.read_brightness()
        self.wait_until(lambda: not self.window._ddc_busy)
        self.assertEqual(self.window.brightness_control.spin.value(), 88)

    def test_demo_section_reads_need_no_confirmation_or_external_access(self):
        with patch("app.QMessageBox.warning", side_effect=AssertionError("dialog shown")):
            self.window.read_picture_section()
            self.wait_until(lambda: not self.window._ddc_busy)
            self.window.read_color_section()
            self.wait_until(lambda: not self.window._ddc_busy)
            self.window.read_audio_section()
            self.wait_until(lambda: not self.window._ddc_busy)
        self.assertEqual(self.window.brightness_control.value(), 70)
        self.assertEqual(self.window.red_control.value(), 50)
        self.assertEqual(self.window.volume_control.value(), 45)
        self.assertFalse(self.window.capabilities_button.isEnabled())
        self.assertFalse(self.window.getvcp_all_button.isEnabled())

    def test_demo_input_source_needs_no_hardware_confirmation(self):
        self.window.select_combo_by_value(self.window.input_combo, 0x11)
        with patch("app.QMessageBox.warning", side_effect=AssertionError("dialog shown")):
            self.window.apply_input_source()
            self.wait_until(lambda: not self.window._ddc_busy)
        self.assertEqual(self.window.backend.get_input_source(0).selector, 0x11)

    def test_demo_languages_keep_selected_monitor_and_page(self):
        self.window.monitor_combo.setCurrentIndex(1)
        self.window.sidebar.setCurrentRow(3)
        self.window.set_language_preference("es")
        self.assertEqual(self.window.sidebar.currentRow(), 3)
        self.assertEqual(self.window.current_monitor_index(), 1)
        self.assertIn("MODO DEMOSTRACIÓN", self.window.findChild(
            type(self.window.overview_label), "demoModeBanner"
        ).text())
        self.window.set_language_preference("en")
        self.assertIn("DEMO MODE", self.window.findChild(
            type(self.window.overview_label), "demoModeBanner"
        ).text())
        self.assertEqual(self.window.current_monitor_index(), 1)

    def test_demo_refresh_only_updates_simulated_monitors(self):
        self.window.backend.set_volume(0, 77)
        self.window.refresh_monitors()
        self.assertEqual(self.window.volume_control.spin.value(), 77)
        self.assertEqual(len(self.window.monitors), 2)

    def test_normal_window_still_uses_real_backend_but_no_startup_queries(self):
        # The non-demo path is verified by its own mocked backend here.
        self.block_real_backend.stop()
        mocked = Mock()
        with patch("app.PlasmaDDCBackend", return_value=mocked):
            regular = app.MainWindow()
            self.assertFalse(regular.demo_mode)
            mocked.refresh_monitors.assert_not_called()
            mocked.build_monitor_profile.assert_not_called()
            regular.close()
            regular.deleteLater()
        self.block_real_backend.start()


class DemoCommandLineTests(unittest.TestCase):
    def test_main_passes_demo_flag_to_window(self):
        fake_app = Mock()
        fake_app.exec.return_value = 0
        with patch("app.QApplication", return_value=fake_app), patch(
            "app.MainWindow"
        ) as fake_window:
            self.assertEqual(app.main(["--demo"]), 0)
            fake_window.assert_called_once_with(demo_mode=True)
            fake_window.return_value.show.assert_called_once()

    def test_launcher_passes_arguments_through(self):
        launcher = Path(__file__).resolve().parents[1] / "run_plasmaddc.sh"
        self.assertIn('"$APP_FILE" "$@"', launcher.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
